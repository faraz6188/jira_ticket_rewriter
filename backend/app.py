from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import requests
from requests.auth import HTTPBasicAuth
import json
import google.generativeai as genai
import os
from dotenv import load_dotenv
import logging
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Jira credentials from environment variables
JIRA_DOMAIN = os.getenv("JIRA_DOMAIN")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# Set up authentication for Jira
auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
headers = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}

app = FastAPI(title="Jira Ticket Rewriter API")

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Models
class Project(BaseModel):
    id: str
    key: str
    name: str
    projectTypeKey: str

class Ticket(BaseModel):
    key: str
    summary: str
    description: Optional[str] = None

class RewrittenTicket(BaseModel):
    key: str
    original_title: str
    rewritten_title: str
    rewritten_description: str
    acceptance_criteria: List[str]
    technical_context: str

class UpdateTicketRequest(BaseModel):
    tickets: List[RewrittenTicket]

# New methods for prompt creation and response parsing
def _create_prompt(ticket_data: dict) -> str:
    """Create a prompt for the AI model with improved context for performance issues"""
    return f"""
    You are an expert in agile development and writing proper user stories. Your task is to rewrite the following Jira ticket as a well-structured user story with acceptance criteria. Focus on translating technical issues into user-centric problems and solutions.

    Ticket Title: {ticket_data.get('summary', 'No Title')}
    
    Ticket Description:
    {ticket_data.get('description', 'No Description')}
    
    Analysis Instructions:
    1. For performance issues (like slow loading, lagging, timeouts):
       - Identify the specific user impact (frustration, abandoned transactions, etc.)
       - Specify measurable performance targets (e.g., "page should load in under 2 seconds")
       - Include technical root causes when possible (e.g., "inefficient database queries")
    
    2. For bug reports:
       - Clearly describe the expected vs. actual behavior
       - Specify the conditions under which the bug occurs
       - Include steps to reproduce when available
    
    3. For feature requests:
       - Focus on the business value and user benefit
       - Be specific about the success criteria
    
    Follow this exact format for your response:
    
    USER STORY:
    As a [specific user role], I want [specific goal related to the issue] so that [clear business benefit].
    
    ACCEPTANCE CRITERIA:
    1. [Specific measurable criterion with clear performance targets]
    2. [Another specific measurable criterion]
    3. [Additional criterion addressing edge cases or related functionality]
    ... (add more as needed)
    
    TECHNICAL CONTEXT:
    [Brief explanation of the technical issue, potential root causes, and why it matters to users and the business]
    """

def _parse_ai_response(response_text: str) -> dict:
    """Parse the AI response into structured data"""
    user_story = ""
    acceptance_criteria = []
    technical_context = ""
    
    # Split response by sections
    sections = response_text.split('\n\n')
    
    # Process each section
    current_section = None
    for section in sections:
        section = section.strip()
        if not section:
            continue
            
        if "USER STORY:" in section:
            current_section = "user_story"
            user_story = section.replace("USER STORY:", "").strip()
        elif "ACCEPTANCE CRITERIA:" in section:
            current_section = "acceptance_criteria"
            criteria_text = section.replace("ACCEPTANCE CRITERIA:", "").strip()
            # Process criteria immediately
            for line in criteria_text.split('\n'):
                line = line.strip()
                if re.match(r'^\d+\.', line):
                    acceptance_criteria.append(line)
        elif "TECHNICAL CONTEXT:" in section:
            current_section = "technical_context"
            technical_context = section.replace("TECHNICAL CONTEXT:", "").strip()
        # Handle multi-line sections
        elif current_section == "user_story":
            user_story += " " + section
        elif current_section == "acceptance_criteria":
            for line in section.split('\n'):
                line = line.strip()
                if re.match(r'^\d+\.', line):
                    acceptance_criteria.append(line)
        elif current_section == "technical_context":
            technical_context += " " + section
    
    # Ensure we have at least some acceptance criteria
    if not acceptance_criteria:
        acceptance_criteria = ["1. The functionality should work as expected."]
    
    # Format the acceptance criteria properly
    formatted_criteria = []
    for criterion in acceptance_criteria:
        # Remove the number prefix if present
        formatted = re.sub(r'^\d+\.\s*', '', criterion)
        if formatted:
            formatted_criteria.append(formatted)
    
    return {
        "user_story": user_story or "As a user, I want this issue resolved so that I can work efficiently.",
        "acceptance_criteria": formatted_criteria or ["The functionality should work as expected."],
        "technical_context": technical_context or "This ticket addresses a technical issue that impacts user experience."
    }

def _generate_better_fallback_response(ticket_data: dict) -> dict:
    """Generate a smarter fallback response when AI fails"""
    summary = ticket_data.get('summary', 'No Title').lower()
    description = ticket_data.get('description', '').lower()
    
    # Check for performance-related keywords
    performance_keywords = ['slow', 'lag', 'performance', 'speed', 'loading', 'timeout']
    is_performance_issue = any(keyword in summary or keyword in description for keyword in performance_keywords)
    
    if is_performance_issue:
        return {
            "user_story": f"As a user, I want the {summary} to respond quickly so that I can complete my tasks efficiently without frustration.",
            "acceptance_criteria": [
                "Page should load in under 2 seconds on standard connection speeds",
                "UI interactions (clicks, scrolls, inputs) should respond within 100ms",
                "All animations should run at 60fps without visual stuttering",
                "Performance should be consistent across supported browsers and devices"
            ],
            "technical_context": f"The {summary} is experiencing performance issues that negatively impact user experience. This could be due to inefficient code, excessive network requests, unoptimized assets, or server-side bottlenecks. Fixing this will improve user satisfaction and potentially increase conversion rates."
        }
    else:
        return {
            "user_story": f"As a user, I want to {summary} so that I can achieve my goals efficiently.",
            "acceptance_criteria": [
                "The functionality should work as expected in all supported browsers",
                "The implementation should meet all business requirements",
                "The solution should be thoroughly tested with automated tests",
                "The solution should maintain or improve current performance metrics"
            ],
            "technical_context": "This ticket addresses a technical issue that impacts user experience and business goals. Proper implementation will ensure system reliability and user satisfaction."
        }
# API Routes
@app.get("/")
async def root():
    return {"message": "Jira Ticket Rewriter API"}

@app.get("/projects", response_model=List[Project])
async def get_projects():
    """Fetch all projects from Jira"""
    url = f"https://{JIRA_DOMAIN}/rest/api/3/project"
    try:
        response = requests.get(url, headers=headers, auth=auth)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch projects: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch projects")

@app.get("/projects/{project_key}/issues", response_model=List[Ticket])
async def get_issues(project_key: str):
    """Fetch issues for a specific project"""
    url = f"https://{JIRA_DOMAIN}/rest/api/3/search"
    payload = json.dumps({
        "jql": f"project = {project_key} ORDER BY created DESC",
        "fields": ["summary", "description"]
    })
    try:
        response = requests.post(url, data=payload, headers=headers, auth=auth)
        response.raise_for_status()
        issues = response.json().get("issues", [])
        
        # Transform the issues to match our model
        formatted_issues = []
        for issue in issues:
            fields = issue.get("fields", {})
            summary = fields.get('summary', 'No summary')
            description = fields.get('description', {})
            description_text = ""
            
            if description and isinstance(description, dict):
                if "content" in description and len(description["content"]) > 0:
                    first_paragraph = description["content"][0]
                    if "content" in first_paragraph and len(first_paragraph["content"]) > 0:
                        first_text_element = first_paragraph["content"][0]
                        if "text" in first_text_element:
                            description_text = first_text_element["text"]
            
            formatted_issues.append({
                "key": issue['key'],
                "summary": summary,
                "description": description_text
            })
        
        return formatted_issues
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch issues: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch issues")
@app.post("/rewrite-tickets", response_model=List[RewrittenTicket])
async def rewrite_tickets(tickets: List[Ticket]):
    """Rewrite selected tickets using Gemini AI with acceptance criteria"""
    rewritten_tickets = []
    
    for ticket in tickets:
        # Create prompt using the improved method
        prompt = _create_prompt({
            "summary": ticket.summary,
            "description": ticket.description or ""
        })
        
        try:
            # Generate content with Gemini API
            response = model.generate_content(prompt)
            
            # Make sure we have text to process
            if not hasattr(response, 'text') or not response.text:
                logger.warning(f"Empty or invalid response from AI for ticket {ticket.key}")
                
                # Use improved fallback response
                parsed_response = _generate_better_fallback_response({
                    "summary": ticket.summary,
                    "description": ticket.description or ""
                })
            else:
                generated_text = response.text
                logger.info(f"AI response for ticket {ticket.key}: {generated_text[:100]}...")
                
                # Parse the AI response using improved parser
                parsed_response = _parse_ai_response(generated_text)
            
            # Extract components
            user_story = parsed_response["user_story"]
            acceptance_criteria = parsed_response["acceptance_criteria"]
            technical_context = parsed_response["technical_context"]
            
            # Make sure we have valid lists for acceptance criteria
            if not isinstance(acceptance_criteria, list):
                acceptance_criteria = [acceptance_criteria] if acceptance_criteria else []
            
            # Ensure numbered format for acceptance criteria
            numbered_criteria = []
            for i, criterion in enumerate(acceptance_criteria, 1):
                # Remove any existing numbers
                clean_criterion = re.sub(r'^\d+\.\s*', '', criterion)
                numbered_criteria.append(f"{i}. {clean_criterion}")
            
            # Format description from user story and technical context
            description = f"{user_story}\n\n{technical_context}"
            
            rewritten_tickets.append({
                "key": ticket.key,
                "original_title": ticket.summary,
                "rewritten_title": user_story,
                "rewritten_description": description,
                "acceptance_criteria": numbered_criteria,
                "technical_context": technical_context
            })
            
        except Exception as e:
            logger.error(f"Failed to generate user story for {ticket.key}: {str(e)}")
            # Use improved fallback values
            parsed_response = _generate_better_fallback_response({
                "summary": ticket.summary,
                "description": ticket.description or ""
            })
            
            user_story = parsed_response["user_story"]
            acceptance_criteria = parsed_response["acceptance_criteria"]
            technical_context = parsed_response["technical_context"]
            
            # Make sure we have valid lists for acceptance criteria
            if not isinstance(acceptance_criteria, list):
                acceptance_criteria = [acceptance_criteria] if acceptance_criteria else []
            
            # Ensure numbered format for acceptance criteria
            numbered_criteria = []
            for i, criterion in enumerate(acceptance_criteria, 1):
                # Remove any existing numbers
                clean_criterion = re.sub(r'^\d+\.\s*', '', criterion)
                numbered_criteria.append(f"{i}. {clean_criterion}")
            
            rewritten_tickets.append({
                "key": ticket.key,
                "original_title": ticket.summary,
                "rewritten_title": user_story,
                "rewritten_description": f"{user_story}\n\n{technical_context}",
                "acceptance_criteria": numbered_criteria,
                "technical_context": technical_context
            })
    
    if not rewritten_tickets:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate any user stories"
        )
    
    return rewritten_tickets

@app.put("/update-tickets")
async def update_tickets(request: UpdateTicketRequest):
    """Update tickets in Jira with rewritten content including acceptance criteria"""
    updated_tickets = []
    failed_tickets = []
    
    for ticket in request.tickets:
        try:
            # Format description to include acceptance criteria
            formatted_description = ticket.rewritten_description + "\n\n"
            formatted_description += "Acceptance Criteria:\n"
            for i, criterion in enumerate(ticket.acceptance_criteria, 1):
                formatted_description += f"{i}. {criterion}\n"
            
            url = f"https://{JIRA_DOMAIN}/rest/api/3/issue/{ticket.key}"
            
            # Format the description for Jira's Atlassian Document Format
            adf_content = []
            
            # Add main description paragraph
            description_paras = ticket.rewritten_description.split('\n\n')
            for para in description_paras:
                if para.strip():
                    adf_content.append({
                        "type": "paragraph",
                        "content": [{
                            "type": "text",
                            "text": para.strip()
                        }]
                    })
            
            # Add acceptance criteria heading
            adf_content.append({
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{
                    "type": "text",
                    "text": "Acceptance Criteria"
                }]
            })
            
            # Add acceptance criteria as bullet list
            list_items = []
            for criterion in ticket.acceptance_criteria:
                list_items.append({
                    "type": "listItem",
                    "content": [{
                        "type": "paragraph",
                        "content": [{
                            "type": "text",
                            "text": criterion
                        }]
                    }]
                })
            
            adf_content.append({
                "type": "bulletList",
                "content": list_items
            })
            
            payload = json.dumps({
                "fields": {
                    "summary": ticket.rewritten_title,
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": adf_content
                    }
                }
            })
            
            response = requests.put(url, data=payload, headers=headers, auth=auth)
            response.raise_for_status()
            updated_tickets.append(ticket.key)
        except Exception as e:
            logger.error(f"Failed to update ticket {ticket.key}: {str(e)}")
            failed_tickets.append({"key": ticket.key, "error": str(e)})
    
    return {
        "success": len(updated_tickets) > 0,
        "updated_tickets": updated_tickets,
        "failed_tickets": failed_tickets
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)