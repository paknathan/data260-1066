var { useState, useEffect } = React;
var { useHistory, useLocation } = ReactRouterDOM;

function Home() {
  const [incidents, setIncidents] = useState([]);
  const [error, setError] = useState('');
  const history = useHistory();
  const location = useLocation(); // Triggers refetch on navigation

  const fetchIncidents = async () => {
    try {
      const response = await fetch('/incidents?skip=0&limit=50', {
        credentials: 'include'
      });
      if (!response.ok) throw new Error('Failed to fetch records');
      const data = await response.json();
      setIncidents(data);
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    fetchIncidents();
  }, [location.pathname]); // Refetches every time route changes to '/'

  const handleDelete = async (id) => {
    try {
      const response = await fetch(`/incidents/${id}`, {
        method: 'DELETE',
        credentials: 'include'
      });
      if (!response.ok) throw new Error('Failed to delete record');
      fetchIncidents();
    } catch (err) {
      alert(err.message);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h2>Municipal Transit Incidents</h2>
        <div>
          <button 
            onClick={() => history.push('/create')} 
            style={{ padding: '8px 12px', backgroundColor: '#28a745', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', marginRight: '8px' }}
          >
            + Add Record
          </button>
          <button 
            onClick={() => history.push('/update')} 
            style={{ padding: '8px 12px', backgroundColor: '#ffc107', color: '#000', border: 'none', borderRadius: '4px', cursor: 'pointer', marginRight: '8px' }}
          >
            Update Record
          </button>
          <button 
            onClick={() => history.push('/delete')} 
            style={{ padding: '8px 12px', backgroundColor: '#dc3545', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
          >
            Delete Record
          </button>
        </div>
      </div>

      {error && <p style={{ color: 'red' }}>{error}</p>}

      <table border="1" cellPadding="10" style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ backgroundColor: '#f2f2f2' }}>
            <th>ID</th>
            <th>Title / Route</th>
            <th>Incident Code</th>
            <th>Delay (Min)</th>
            <th>Congestion ID</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {incidents.length > 0 ? (
            incidents.map((item) => (
              <tr key={item.id}>
                <td>{item.id}</td>
                <td>{item.title}</td>
                <td>{item.incident_code}</td>
                <td>{item.delay_minutes}</td>
                <td>{item.congestion_index_id}</td>
                <td>
                  <button onClick={() => handleDelete(item.id)} style={{ color: 'red', cursor: 'pointer' }}>Delete</button>
                </td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan="6" style={{ textAlign: 'center' }}>No incident records found.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

window.Home = Home;