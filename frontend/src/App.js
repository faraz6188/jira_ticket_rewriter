import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './App.css';

const API_BASE_URL = 'http://localhost:8000';

function App() {
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [tickets, setTickets] = useState([]);
  const [selectedTickets, setSelectedTickets] = useState([]);
  const [rewrittenTickets, setRewrittenTickets] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [selectAll, setSelectAll] = useState(false);

  useEffect(() => {
    fetchProjects();
  }, []);

  const fetchProjects = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${API_BASE_URL}/projects`);
      setProjects(response.data);
      setError(null);
    } catch (err) {
      setError('Failed to fetch projects. Please check your API connection.');
      console.error('Error fetching projects:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleProjectSelect = async (project) => {
    setSelectedProject(project);
    setSelectedTickets([]);
    setRewrittenTickets([]);
    setLoading(true);
    
    try {
      const response = await axios.get(`${API_BASE_URL}/projects/${project.key}/issues`);
      const formattedTickets = response.data.map(ticket => ({
        ...ticket,
        isRewritten: false
      }));
      setTickets(formattedTickets);
      setError(null);
    } catch (err) {
      setError(`Failed to fetch tickets for project ${project.name}.`);
      console.error('Error fetching tickets:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleTicketSelect = (ticket) => {
    setSelectedTickets(prev => {
      if (prev.some(t => t.key === ticket.key)) {
        return prev.filter(t => t.key !== ticket.key);
      } else {
        return [...prev, ticket];
      }
    });
    
    // Update select all checkbox state
    if (selectedTickets.length === tickets.length - 1) {
      setSelectAll(true);
    } else {
      setSelectAll(false);
    }
  };

  const handleSelectAll = () => {
    if (selectAll) {
      // Deselect all tickets
      setSelectedTickets([]);
    } else {
      // Select all tickets
      setSelectedTickets(tickets);
    }
    setSelectAll(!selectAll);
  };

  const handleRewriteTickets = async () => {
    if (selectedTickets.length === 0) {
      setError('Please select at least one ticket to rewrite.');
      return;
    }
    
    setLoading(true);
    setError(null);
    
    try {
      const response = await axios.post(`${API_BASE_URL}/rewrite-tickets`, selectedTickets);
      setRewrittenTickets(response.data);
      setSuccess('Tickets rewritten successfully!');
      
      const updatedTickets = tickets.map(ticket => {
        if (selectedTickets.some(t => t.key === ticket.key)) {
          return {
            ...ticket,
            isRewritten: true
          };
        }
        return ticket;
      });
      setTickets(updatedTickets);
    } catch (err) {
      setError('Failed to rewrite tickets. Please try again.');
      console.error('Error rewriting tickets:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateTickets = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await axios.put(`${API_BASE_URL}/update-tickets`, {
        tickets: rewrittenTickets
      });
      
      if (response.data.success) {
        setSuccess('Tickets updated successfully in Jira!');
        setRewrittenTickets([]);
        setSelectedTickets([]);
        
        if (selectedProject) {
          const ticketsResponse = await axios.get(`${API_BASE_URL}/projects/${selectedProject.key}/issues`);
          const formattedTickets = ticketsResponse.data.map(ticket => ({
            ...ticket,
            isRewritten: tickets.find(t => t.key === ticket.key)?.isRewritten || false
          }));
          setTickets(formattedTickets);
        }
      } else {
        setError(`Some tickets failed to update: ${response.data.failed_tickets.map(t => t.key).join(', ')}`);
      }
    } catch (err) {
      setError('Failed to update tickets in Jira. Please try again.');
      console.error('Error updating tickets:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDescriptionChange = (key, newDescription) => {
    setRewrittenTickets(prev => 
      prev.map(ticket => 
        ticket.key === key ? {...ticket, rewritten_description: newDescription} : ticket
      )
    );
  };

  // Add this useEffect to automatically dismiss messages after 5 seconds
  useEffect(() => {
    if (error || success) {
      const timer = setTimeout(() => {
        setError(null);
        setSuccess(null);
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [error, success]);

  return (
    <div className="App">
      <header className="App-header">
        <div className="logo-container">
          <span className="logo-icon">📝</span>
          <h1>Jira Ticket Rewriter</h1>
        </div>
        <div className="header-actions">
          <button 
            className="action-button icon-button"
            onClick={() => window.location.reload()}
          >
            <span className="button-icon">🔄</span>
          </button>
        </div>
      </header>
      
      <main className="App-main">
        <section className="projects-section card">
          <h2>Projects</h2>
          {loading && projects.length === 0 ? (
            <div className="loading-indicator">Loading projects...</div>
          ) : (
            <div className="project-list">
              {projects.map(project => (
                <div 
                  key={project.id} 
                  className={`project-card ${selectedProject?.id === project.id ? 'active' : ''}`}
                  onClick={() => handleProjectSelect(project)}
                >
                  <div className="project-info">
                    <h3>{project.name}</h3>
                    <div className="project-meta">
                      <span>Key: {project.key}</span>
                      <span>Type: {project.projectTypeKey}</span>
                    </div>
                  </div>
                  {selectedProject?.id === project.id && (
                    <span className="selected-indicator">Selected</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
        
        {selectedProject && (
          <div className="content-wrapper">
            <section className="tickets-section card">
              <div className="section-header">
                <h2>Jira Tickets</h2>
                <div className="section-actions">
                  <button 
                    className="action-button secondary"
                    onClick={() => handleProjectSelect(selectedProject)}
                    disabled={loading}
                  >
                    <span className="button-icon">🔄</span> Refresh
                  </button>
                </div>
              </div>
              
              <div className="selection-controls">
                <div className="select-all">
                  <label>
                    <input
                      type="checkbox"
                      checked={selectAll}
                      onChange={handleSelectAll}
                    />
                    Select All
                  </label>
                </div>
                <div className="selection-info">
                  {selectedTickets.length} of {tickets.length} selected
                </div>
              </div>
              
              {loading && tickets.length === 0 ? (
                <div className="loading-indicator">Loading tickets...</div>
              ) : (
                <div className="ticket-list">
                  {tickets.map(ticket => (
                    <div key={ticket.key} className="ticket-card">
                      <div className="ticket-selector">
                        <input
                          type="checkbox"
                          checked={selectedTickets.some(t => t.key === ticket.key)}
                          onChange={() => handleTicketSelect(ticket)}
                          id={`ticket-${ticket.key}`}
                        />
                        <label htmlFor={`ticket-${ticket.key}`} className="ticket-label">
                          <span className="ticket-key">{ticket.key}</span>: {ticket.summary}
                          {ticket.isRewritten && <span className="status-badge">Rewritten</span>}
                        </label>
                      </div>
                      <div className="ticket-description">
                        {ticket.description || 'No description provided'}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              
              <div className="action-bar">
                <button 
                  className="action-button primary"
                  onClick={handleRewriteTickets}
                  disabled={loading || selectedTickets.length === 0}
                >
                  <span className="button-icon">📝</span> Rewrite Selected Tickets
                </button>
              </div>
            </section>
            
            <section className="rewritten-section card">
              <h2>Rewritten Tickets</h2>
              
              {loading && (
                <div className="loading-indicator">Processing tickets...</div>
              )}
              
              {rewrittenTickets.length > 0 ? (
                <>
                  <div className="rewritten-list">
                    {rewrittenTickets.map(ticket => (
                      <div key={ticket.key} className="rewritten-card">
                        <div className="rewritten-header">
                          <h3>Original: {ticket.original_title}</h3>
                          <h4>Rewritten: {ticket.rewritten_title}</h4>
                        </div>
                        <div className="rewritten-content">
                          <textarea
                            value={ticket.rewritten_description}
                            onChange={(e) => handleDescriptionChange(ticket.key, e.target.value)}
                            placeholder="Edit rewritten description..."
                            rows={4}
                          />
                          <div className="acceptance-criteria">
                            <h5>Acceptance Criteria:</h5>
                            <ul>
                              {ticket.acceptance_criteria.map((criterion, index) => (
                                <li key={index}>{criterion}</li>
                              ))}
                            </ul>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="action-bar">
                    <button 
                      className="action-button success"
                      onClick={handleUpdateTickets}
                      disabled={loading}
                    >
                      <span className="button-icon">✅</span> Approve & Update Jira
                    </button>
                  </div>
                </>
              ) : (
                <div className="empty-state">
                  <p>No rewritten tickets yet. Select tickets and click 'Rewrite Selected Tickets'.</p>
                </div>
              )}
            </section>
          </div>
        )}
        
        <div className="messages">
          {error && (
            <div className="message error">
              <span className="message-content">{error}</span>
              <button 
                className="dismiss-button"
                onClick={() => setError(null)}
              >
                ×
              </button>
            </div>
          )}
          {success && (
            <div className="message success">
              <span className="message-content">{success}</span>
              <button 
                className="dismiss-button"
                onClick={() => setSuccess(null)}
              >
                ×
              </button>
            </div>
          )}
        </div>
      </main>
      <footer className="App-footer">
        <div className="footer-content">
          <span>© 2025 Jira Ticket Rewriter</span>
        </div>
      </footer>
    </div>
  );
}

export default App;