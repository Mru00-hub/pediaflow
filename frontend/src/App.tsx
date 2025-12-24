import { useState } from 'react';
import { usePediaFlow } from './usePediaFlow';
import { InputForm } from './components/InputForm';
import { PrescriptionCard } from './components/PrescriptionCard';
import { TrajectoryChart } from './components/TrajectoryChart';
import { TankVisualizer } from './components/TankVisualizer';
import { SimulationPanel } from './components/SimulationPanel';
import { PatientInput } from './types'; 

function App() {
  const { generatePlan, prescription, loading, error, reset } = usePediaFlow();
  const [patientData, setPatientData] = useState<PatientInput | null>(null);
  const handleFormSubmit = (data: PatientInput) => {
    setPatientData(data); // Store for Simulator
    generatePlan(data);   // Generate Standard Plan
  };

  const handleReset = () => {
    reset();
    setPatientData(null);
  };

  return (
    <div className="min-h-screen bg-slate-100 p-4 md:p-8 font-sans text-slate-900">
      
      {/* Header */}
      <header className="max-w-5xl mx-auto mb-8 flex items-center justify-between">
        <div>
           <h1 className="text-2xl md:text-3xl font-bold text-slate-800 tracking-tight">PediaFlow <span className="text-blue-600">AI</span></h1>
           <p className="text-slate-500 text-sm">Pediatric Hemodynamic Digital Twin</p>
        </div>
        <div className="bg-amber-100 text-amber-800 text-xs px-3 py-1 rounded-full font-semibold border border-amber-200">
           ⚠️ Clinical Decision Support Only
        </div>
      </header>

      <main className="max-w-5xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8">
        
        {/* LEFT COLUMN: Input */}
        <div className="lg:col-span-5 space-y-6">
          <InputForm onSubmit={generatePlan} loading={loading} />
          {error && (
            <div className="bg-red-50 text-red-700 p-4 rounded-lg border border-red-200 text-sm">
              <strong>Engine Error:</strong> {error}
            </div>
          )}
        </div>

        {/* RIGHT COLUMN: Output or Placeholder */}
        <div className="lg:col-span-7">
          {prescription ? (
            <div className="space-y-6">
               <div className="flex justify-between items-center">
                  <h3 className="text-lg font-bold text-slate-700">Simulation Result</h3>
                  <button onClick={reset} className="text-sm text-blue-600 hover:underline">Clear</button>
               </div>
               {/* 1. Prescription Card with Metronome */}
               <PrescriptionCard data={prescription} />
               
               {/* Phase 3: Visual Intelligence */}
               <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Left: The Physics (Tanks) */}
                  <TankVisualizer data={prescription} />
                  
                  {/* Right: The Prediction (Graph) */}
                  <TrajectoryChart data={prescription.trajectory} />
               </div>
              {patientData && (
                  <SimulationPanel patient={patientData} />
               )}
            </div>
          ) : (
            // Empty State
            <div className="h-full flex flex-col items-center justify-center text-slate-400 space-y-4 min-h-[400px] border-2 border-dashed border-slate-200 rounded-xl">
               <div className="w-16 h-16 bg-slate-200 rounded-full flex items-center justify-center">
                 <span className="text-2xl">⚡️</span>
               </div>
               <p>Enter patient vitals to generate a Digital Twin simulation.</p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
