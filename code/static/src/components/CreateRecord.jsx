var { useState } = React;
var { useHistory } = ReactRouterDOM;

function CreateRecord() {
  const [title, setTitle] = useState('');
  const [incidentCode, setIncidentCode] = useState('');
  const [delayMinutes, setDelayMinutes] = useState(15);
  const [congestionIndexId, setCongestionIndexId] = useState(1);
  const [error, setError] = useState('');

  const history = useHistory();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    const payload = {
      title,
      incident_code: incidentCode,
      delay_minutes: parseInt(delayMinutes, 10),
      congestion_index_id: parseInt(congestionIndexId, 10)
    };

    try {
      const response = await fetch('/incidents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to create record.');
      }

      history.push('/');
    } catch (err) {
      setError(err.message || 'Failed to create record.');
    }
  };

  return (
    <div style={{ maxWidth: '500px', margin: '0 auto' }}>
      <h3>Add New Incident Record</h3>
      {error && <p style={{ color: 'red' }}>{error}</p>}
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: '15px' }}>
          <label style={{ display: 'block' }}>Title / Route:</label>
          <input 
            type="text" 
            value={title} 
            onChange={(e) => setTitle(e.target.value)} 
            placeholder="e.g. CA-85 N Collision"
            required 
            style={{ width: '100%', padding: '8px' }} 
          />
        </div>
        <div style={{ marginBottom: '15px' }}>
          <label style={{ display: 'block' }}>Incident Code:</label>
          <input 
            type="text" 
            value={incidentCode} 
            onChange={(e) => setIncidentCode(e.target.value)} 
            placeholder="e.g. INC-2026-001"
            required 
            style={{ width: '100%', padding: '8px' }} 
          />
        </div>
        <div style={{ marginBottom: '15px' }}>
          <label style={{ display: 'block' }}>Delay (Minutes):</label>
          <input 
            type="number" 
            value={delayMinutes} 
            onChange={(e) => setDelayMinutes(e.target.value)} 
            required 
            style={{ width: '100%', padding: '8px' }} 
          />
        </div>
        <div style={{ marginBottom: '15px' }}>
          <label style={{ display: 'block' }}>Congestion Index ID (FK):</label>
          <input 
            type="number" 
            value={congestionIndexId} 
            onChange={(e) => setCongestionIndexId(e.target.value)} 
            required 
            style={{ width: '100%', padding: '8px' }} 
          />
        </div>
        <button type="submit" style={{ padding: '8px 16px', backgroundColor: '#28a745', color: '#fff', border: 'none', cursor: 'pointer' }}>
          Add Record
        </button>
      </form>
    </div>
  );
}

window.CreateRecord = CreateRecord;