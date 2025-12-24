// TestConnection.tsx
import React, { useEffect } from 'react';
import { usePediaFlow } from './usePediaFlow';
import { ClinicalDiagnosis, IVSetType, OngoingLosses } from './types';

export const TestConnection = () => {
  const { generatePlan, prescription, loading, error } = usePediaFlow();

  const handleTest = () => {
    // Hardcoded test case based on your 'debug_calibration.py'
    generatePlan({
      age_months: 60,
      weight_kg: 18.0,
      sex: 'M',
      muac_cm: 15.0,
      temp_celsius: 37.0,
      systolic_bp: 100,
      heart_rate: 120,
      respiratory_rate_bpm: 60,
      sp_o2_percent: 85,
      capillary_refill_sec: 2,
      hemoglobin_g_dl: 12.0,
      diagnosis: ClinicalDiagnosis.UNKNOWN,
      ongoing_losses_severity: OngoingLosses.NONE,
      iv_set_available: IVSetType.MICRO_DRIP
    });
  };

  return (
    <div className="p-4 border rounded shadow-md max-w-lg mx-auto mt-10">
      <h2 className="text-xl font-bold mb-4">API Integration Check</h2>
      
      <button 
        onClick={handleTest}
        disabled={loading}
        className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? 'Calculating...' : 'Run Test Case'}
      </button>

      {error && (
        <div className="mt-4 p-3 bg-red-100 text-red-700 border border-red-300 rounded">
          <strong>Error:</strong> {error}
        </div>
      )}

      {prescription && (
        <div className="mt-4 p-3 bg-green-50 text-green-900 border border-green-300 rounded">
          <h3 className="font-bold">Success!</h3>
          <p>{prescription.human_readable_summary}</p>
          <div className="mt-2 text-sm text-gray-600">
            Rate: {prescription.drops_per_minute} drops/min ({prescription.seconds_per_drop} sec/drop)
          </div>
        </div>
      )}
    </div>
  );
};
