// usePediaFlow.ts
import { useState } from 'react';
import { api } from './api';
import { PatientInput, PrescriptionResponse } from './types';

export const usePediaFlow = () => {
  const [prescription, setPrescription] = useState<PrescriptionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generatePlan = async (patientData: PatientInput) => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.getPrescription(patientData);
      setPrescription(result);
    } catch (err: any) {
      console.error(err);
      setError(err.message || "Failed to generate prescription");
      setPrescription(null);
    } finally {
      setLoading(false);
    }
  };

  return {
    generatePlan,
    prescription,
    loading,
    error,
    reset: () => { setPrescription(null); setError(null); }
  };
};
