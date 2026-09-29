var { useState } = React;
var { useHistory } = ReactRouterDOM;

function DeleteRecord() {
  const [incidentId, setIncidentId] = useState('');
  const [error, setError] = useState('');
  const history = useHistory();

  const handleDelete = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch(`/incidents/${incidentId}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      if (!response.ok) throw new Error('Failed to delete record.');
      history.push('/');
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div style={{ maxWidth: '500px', margin: '0 auto' }}>
      <h3>Delete Record</h3>
      {error && <p style={{ color: 'red' }}>{error}</p>}
      <form onSubmit={handleDelete}>
        <div style={{ marginBottom: '15px' }}>
          <label style={{ display: 'block' }}>Incident ID to Delete:</label>
          <input type="text" value={incidentId} onChange={(e) => setIncidentId(e.target.value)} required placeholder="e.g. INC-00147" style={{ width: '100%', padding: '8px' }} />
        </div>
        <button type="submit" style={{ padding: '8px 16px', backgroundColor: '#dc3545', color: '#fff', border: 'none' }}>Delete Record</button>
      </form>
    </div>
  );
}

window.DeleteRecord = DeleteRecord;