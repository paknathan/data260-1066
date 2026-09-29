var { useState } = React;
var { useHistory } = ReactRouterDOM;

function CreateRecord() {
  const [routeOrLine, setRouteOrLine] = useState('');
  const [incidentType, setIncidentType] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');
  const history = useHistory();

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch('/incidents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ route_or_line: routeOrLine, incident_type: incidentType, description }),
      });
      if (!response.ok) throw new Error('Failed to create record.');
      history.push('/');
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div style={{ maxWidth: '500px', margin: '0 auto' }}>
      <h3>Add New Incident Record</h3>
      {error && <p style={{ color: 'red' }}>{error}</p>}
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: '15px' }}>
          <label style={{ display: 'block' }}>Route or Line (Primary Field):</label>
          <input type="text" value={routeOrLine} onChange={(e) => setRouteOrLine(e.target.value)} required style={{ width: '100%', padding: '8px' }} />
        </div>
        <div style={{ marginBottom: '15px' }}>
          <label style={{ display: 'block' }}>Incident Type (Secondary Field):</label>
          <input type="text" value={incidentType} onChange={(e) => setIncidentType(e.target.value)} required style={{ width: '100%', padding: '8px' }} />
        </div>
        <div style={{ marginBottom: '15px' }}>
          <label style={{ display: 'block' }}>Description:</label>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} style={{ width: '100%', padding: '8px' }} />
        </div>
        <button type="submit" style={{ padding: '8px 16px', backgroundColor: '#28a745', color: '#fff', border: 'none' }}>Add Record</button>
      </form>
    </div>
  );
}

window.CreateRecord = CreateRecord;