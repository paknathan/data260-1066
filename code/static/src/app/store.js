// Configure redux store with the incidents reducer
import { configureStore } from '@reduxjs/toolkit';
import incidentsReducer from '../../../src/features/incidentsSlice';

export const store = configureStore({
  reducer: {
    incidents: incidentsReducer,
  },
});