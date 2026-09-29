var { useState, useEffect } = React;
var { Link } = ReactRouterDOM;

function Home({ isAuthenticated }) {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchId, setSearchId] = useState('');

  useEffect(() => {
    if (isAuthenticated) {
      fetchAllRecords();
    } else {
      setLoading(false);
    }
  }, [isAuthenticated]);

  const fetchAllRecords = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch('/incidents', { credentials: 'include' });
      if (!response.ok) throw new Error('Failed to fetch records.');
      const data = await response.json();
      setRecords(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // View a record by ID (GET /incidents/{id})
  const handleSearchById = async (e) => {
    e.preventDefault();
    if (!searchId.trim()) {
      fetchAllRecords();
      return;
    }

    setLoading(true);
    setError('');
    try {
      const response = await fetch(`/incidents/${searchId.trim()}`, { credentials: 'include' });
      if (!response.ok) {
        if (response.status === 404) throw new Error(`Incident with ID ${searchId} not found.`);
        throw new Error('Failed to fetch record by ID.');
      }
      const data = await response.json();
      setRecords([data]); // Display only the retrieved record
    } catch (err) {
      setRecords([]);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleResetSearch = () => {
    setSearchId('');
    fetchAllRecords();
  };

  if (!isAuthenticated) {
    return (
      <div style={{ textAlign: 'center', marginTop: '50px' }}>
        <h2>Login required</h2>
        <p>Please log in to view transit incident records and perform CRUD operations.</p>
        <Link to="/login" style={{ color: '#007bff', fontWeight: 'bold' }}>Go to Login</Link>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h3>Municipal Transit Incidents</h3>
        <div>
          <Link to="/create" style={{ padding: '8px 12px', backgroundColor: '#28a745', color: '#fff', textDecoration: 'none', borderRadius: '4px', marginRight: '8px' }}>+ Add Record</Link>
          <Link to="/update" style={{ padding: '8px 12px', backgroundColor: '#ffc107', color: '#000', textDecoration: 'none', borderRadius: '4px', marginRight: '8px' }}>Update Record</Link>
          <Link to="/delete" style={{ padding: '8px 12px', backgroundColor: '#dc3545', color: '#fff', textDecoration: 'none', borderRadius: '4px' }}>Delete Record</Link>
        </div>
      </div>

      {/* View Record by ID Form */}
      <form onSubmit={handleSearchById} style={{ marginBottom: '20px', display: 'flex', gap: '10px', alignItems: 'center' }}>
        <input
          type="number"
          value={searchId}
          onChange={(e) => setSearchId(e.target.value)}
          placeholder="Enter Incident ID (e.g. 1)"
          style={{ padding: '8px', width: '220px' }}
        />
        <button type="submit" style={{ padding: '8px 16px', backgroundColor: '#007bff', color: '#fff', border: 'none', cursor: 'pointer', borderRadius: '4px' }}>
          Find Record
        </button>
        {searchId && (
          <button type="button" onClick={handleResetSearch} style={{ padding: '8px 16px', backgroundColor: '#6c757d', color: '#fff', border: 'none', cursor: 'pointer', borderRadius: '4px' }}>
            Show All Records
          </button>
        )}
      </form>

      {loading && <p>Loading records...</p>}
      {error && <p style={{ color: 'red' }}>{error}</p>}

      {!loading && !error && (
        <table border="1" cellPadding="10" cellSpacing="0" style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ backgroundColor: '#f2f2f2' }}>
              <th>Incident ID</th>
              <th>Route / Line (Primary)</th>
              <th>Incident Type (Secondary)</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {records.length > 0 ? (
              records.map((item) => (
                <tr key={item.incident_id}>
                  <td>{item.incident_id}</td>
                  <td>{item.route_or_line}</td>
                  <td>{item.incident_type}</td>
                  <td>{item.description}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan="4" style={{ textAlign: 'center' }}>No incident records found.</td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}

window.Home = Home;