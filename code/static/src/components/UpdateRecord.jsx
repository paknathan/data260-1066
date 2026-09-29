var { useState } = React;
var { useHistory } = ReactRouterDOM;

function UpdateRecord() {
  const [incidentId, setIncidentId] = useState('');
  const [routeOrLine, setRouteOrLine] = useState('');
  const [incidentType, setIncidentType] = useState('');
  const [error, setError] = useState('');
  const history = useHistory();

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch(`/incidents/${incidentId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ route_or_line: routeOrLine, incident_type: incidentType }),
      });
      if (!response.ok) throw new Error('Failed to update record.');
      history.push('/');
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div style={{ maxWidth: '500px', margin: '0 auto' }}>
      <h3>Update Record</h3>
      {error && <p style={{ color: 'red' }}>{error}</p>}
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: '15px' }}>
          <label style={{ display: 'block' }}>Incident ID to Update:</label>
          <input type="text" value={incidentId} onChange={(e) => setIncidentId(e.target.value)} required placeholder="e.g. INC-00147" style={{ width: '100%', padding: '8px' }} />
        </div>
        <div style={{ marginBottom: '15px' }}>
          <label style={{ display: 'block' }}>New Route / Line:</label>
          <input type="text" value={routeOrLine} onChange={(e) => setRouteOrLine(e.target.value)} required style={{ width: '100%', padding: '8px' }} />
        </div>
        <div style={{ marginBottom: '15px' }}>
          <label style={{ display: 'block' }}>New Incident Type:</label>
          <input type="text" value={incidentType} onChange={(e) => setIncidentType(e.target.value)} required style={{ width: '100%', padding: '8px' }} />
        </div>
        <button type="submit" style={{ padding: '8px 16px', backgroundColor: '#ffc107', border: 'none' }}>Update Record</button>
      </form>
    </div>
  );
}

window.UpdateRecord = UpdateRecord;