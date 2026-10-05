var { useState } = React;
var { useHistory } = ReactRouterDOM;

function UpdateRecord() {
  const [id, setId] = useState('');
  const [title, setTitle] = useState('');
  const [incidentCode, setIncidentCode] = useState('');
  const [delayMinutes, setDelayMinutes] = useState('');
  const [congestionIndexId, setCongestionIndexId] = useState('');
  const [error, setError] = useState('');
  const history = useHistory();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

   const payload = {};
if (title.trim()) payload.title = title;
if (incidentCode.trim()) payload.incident_code = incidentCode;
if (delayMinutes !== '') payload.delay_minutes = parseInt(delayMinutes, 10);
if (congestionIndexId !== '') payload.congestion_index_id = parseInt(congestionIndexId, 10);

    try {
      const response = await fetch(`/incidents/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to update record.');
      }

      history.push('/');
    } catch (err) {
      setError(err.message || 'Failed to update record.');
    }
  };

  return (
    <div style={{ maxWidth: '500px', margin: '0 auto' }}>
      <h3>Update Incident Record</h3>
      {error && <p style={{ color: 'red' }}>{error}</p>}
      
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: '15px' }}>
          <label style={{ display: 'block' }}>Incident Numeric ID (e.g., 3):</label>
          <input
            type="number"
            value={id}
            onChange={(e) => setId(e.target.value)}
            required
            style={{ width: '100%', padding: '8px' }}
          />
        </div>

        <div style={{ marginBottom: '15px' }}>
          <label style={{ display: 'block' }}>New Title / Route:</label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. US-101 N Collision"
            style={{ width: '100%', padding: '8px' }}
          />
        </div>

        <div style={{ marginBottom: '15px' }}>
          <label style={{ display: 'block' }}>New Incident Code:</label>
          <input
            type="text"
            value={incidentCode}
            onChange={(e) => setIncidentCode(e.target.value)}
            placeholder="e.g. INC-2026-999"
            style={{ width: '100%', padding: '8px' }}
          />
        </div>

        <div style={{ marginBottom: '15px' }}>
          <label style={{ display: 'block' }}>New Delay (Minutes):</label>
          <input
            type="number"
            value={delayMinutes}
            onChange={(e) => setDelayMinutes(e.target.value)}
            placeholder="e.g. 20"
            style={{ width: '100%', padding: '8px' }}
          />
        </div>

        <div style={{ marginBottom: '15px' }}>
          <label style={{ display: 'block' }}>New Congestion Index ID (FK):</label>
          <input
            type="number"
            value={congestionIndexId}
            onChange={(e) => setCongestionIndexId(e.target.value)}
            placeholder="e.g. 1"
            style={{ width: '100%', padding: '8px' }}
          />
        </div>

        <button type="submit" style={{ padding: '10px 15px', backgroundColor: '#ffc107', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
          Update Record
        </button>
      </form>
    </div>
  );
}

window.UpdateRecord = UpdateRecord;