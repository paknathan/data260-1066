import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';

const API_URL = 'http://127.0.0.1:8166/incidents';

// Async Thunks
export const fetchIncidents = createAsyncThunk('incidents/fetchIncidents', async () => {
  const response = await axios.get(`${API_URL}?skip=0&limit=10`, { withCredentials: true });
  return response.data;
});

export const createIncident = createAsyncThunk('incidents/createIncident', async (newIncident) => {
  const response = await axios.post(API_URL, newIncident, { withCredentials: true });
  return response.data;
});

export const updateIncident = createAsyncThunk('incidents/updateIncident', async ({ id, data }) => {
  const response = await axios.put(`${API_URL}/${id}`, data, { withCredentials: true });
  return response.data;
});

export const deleteIncident = createAsyncThunk('incidents/deleteIncident', async (id) => {
  await axios.delete(`${API_URL}/${id}`, { withCredentials: true });
  return id;
});

// Slice Definition
const incidentsSlice = createSlice({
  name: 'incidents',
  initialState: { items: [], status: 'idle', error: null },
  reducers: {},
  extraReducers: (builder) => {
    builder
      // Fetch
      .addCase(fetchIncidents.fulfilled, (state, action) => {
        state.items = action.payload;
        state.status = 'succeeded';
      })
      // Create
      .addCase(createIncident.fulfilled, (state, action) => {
        state.items.push(action.payload);
      })
      // Update
      .addCase(updateIncident.fulfilled, (state, action) => {
        const index = state.items.findIndex(item => item.id === action.payload.id);
        if (index !== -1) {
          state.items[index] = action.payload;
        }
      })
      // Delete
      .addCase(deleteIncident.fulfilled, (state, action) => {
        state.items = state.items.filter(item => item.id !== action.payload);
      });
  },
});

export default incidentsSlice.reducer;