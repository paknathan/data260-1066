/* 
Below is the consolidated React component demonstrating the requested features for the Municipal Incidents Dashboard. 
It includes a form for creating and updating incidents, a list of incidents with delete buttons, and state management using Redux Toolkit.
*/
import React, { useEffect, useState } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { fetchIncidents, createIncident, updateIncident, deleteIncident } from '../../../src/features/incidentsSlice';

export default function IncidentsManager() {
  const dispatch = useDispatch();
  const { items: incidents, status } = useSelector((state) => state.incidents);

  const [form, setForm] = useState({ title: '', incident_code: '', delay_minutes: 0, congestion_index_id: 1 });
  const [selectedId, setSelectedId] = useState(null);

  useEffect(() => {
    dispatch(fetchIncidents());
  }, [dispatch]);

  const handleCreate = (e) => {
    e.preventDefault();
    dispatch(createIncident(form));
  };

  const handleUpdate = (e) => {
    e.preventDefault();
    if (selectedId) {
      dispatch(updateIncident({ id: selectedId, data: { delay_minutes: form.delay_minutes } }));
    }
  };

  const handleDelete = (id) => {
    dispatch(deleteIncident(id));
  };

  return (
    <div style={{ padding: '20px' }}>
      <h2>Municipal Incidents Dashboard</h2>

      {/* Create / Update Form */}
      <form style={{ marginBottom: '20px' }}>
        <input 
          placeholder="Title" 
          onChange={(e) => setForm({ ...form, title: e.target.value })} 
        />
        <input 
          placeholder="Code (e.g. INC-2026-001)" 
          onChange={(e) => setForm({ ...form, incident_code: e.target.value })} 
        />
        <input 
          type="number" 
          placeholder="Delay Minutes" 
          onChange={(e) => setForm({ ...form, delay_minutes: parseInt(e.target.value) })} 
        />
        <button onClick={handleCreate}>Add Incident</button>
        <button onClick={handleUpdate}>Update Selected ID ({selectedId})</button>
      </form>

      {/* Home Screen List with Delete Buttons */}
      <ul>
        {incidents.map((inc) => (
          <li key={inc.id} style={{ margin: '8px 0' }}>
            <strong>[{inc.incident_code}] {inc.title}</strong> — {inc.delay_minutes} min delay
            <button onClick={() => setSelectedId(inc.id)} style={{ marginLeft: '10px' }}>Select for Update</button>
            <button onClick={() => handleDelete(inc.id)} style={{ marginLeft: '5px', color: 'red' }}>Delete</button>
          </li>
        ))}
      </ul>
    </div>
  );
}