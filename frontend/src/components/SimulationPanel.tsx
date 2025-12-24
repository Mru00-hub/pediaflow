import React, { useState } from 'react';
import { api } from '../api';
import { PatientInput, FluidType, SimulationResponse, SafetyAlerts } from '../types';
import { TrajectoryChart } from './TrajectoryChart';
import { TankVisualizer } from './TankVisualizer';
import { Play, RotateCcw, Activity } from 'lucide-react';
import clsx from 'clsx';

interface Props {
  patient: PatientInput;
}

// Helper: Convert API Alert Strings to Flags for Visualizer
const mapAlertsToFlags = (alertStrings: string[]): SafetyAlerts => {
  const s = new Set(alertStrings.join(' ').toLowerCase());
  return {
    risk_pulmonary_edema: s.has('pulmonary') || s.has('lung'),
    risk_volume_overload: s.has('volume') || s.has('overload'),
    risk_cerebral_edema: s.has('cerebral') || s.has('brain'),
    risk_hypoglycemia: s.has('hypoglycemia'),
    hydrocortisone_needed: s.has('hydrocortisone'),
    risk_ketoacidosis: s.has('ketoacidosis'),
    sam_heart_warning: s.has('sam') || s.has('weak heart'),
    anemia_dilution_warning: s.has('anemia') || s.has('hemodilution'),
    dengue_leak_warning: s.has('dengue') || s.has('leak')
  };
};

export const SimulationPanel: React.FC<Props> = ({ patient }) => {
  const [fluid, setFluid] = useState<string>(FluidType.RL);
  const [volume, setVolume] = useState<number>(Math.round(patient.weight_kg * 20));
  const [duration, setDuration] = useState<number>(60);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SimulationResponse | null>(null);

  const handleSimulate = async () => {
    setLoading(true);
    try {
      const res = await api.runSimulation({
        patient,
        fluid_type: fluid,
        volume_ml: volume,
        duration_min: duration
      });
      setResult(res);
    } catch (err) {
      console.error(err);
      alert("Simulation failed. Check console.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-slate-900 text-slate-100 rounded-xl overflow-hidden shadow-2xl border border-slate-700 mt-8">
      
      {/* HEADER */}
      <div className="p-4 border-b border-slate-700 flex justify-between items-center bg-slate-800/50">
        <h3 className="font-bold flex items-center gap-2">
          <Activity className="text-blue-400 w-5 h-5" />
          "What-If" Physics Simulator
        </h3>
        <span className="text-xs bg-blue-900/50 text-blue-200 px-2 py-1 rounded border border-blue-800">
           Experimental
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12">
        
        {/* CONTROLS */}
        <div className="lg:col-span-4 p-6 space-y-8 border-r border-slate-700 bg-slate-800/20">
          
          <div className="space-y-2">
            <label className="text-xs font-bold text-slate-400 uppercase tracking-wider">Fluid Type</label>
            <select 
              value={fluid} 
              onChange={(e) => setFluid(e.target.value)}
              className="w-full bg-slate-800 border border-slate-600 rounded p-3 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
            >
              <option value={FluidType.RL}>Ringer Lactate</option>
              <option value={FluidType.NS}>Normal Saline (0.9%)</option>
              <option value={FluidType.D5_NS}>D5 Normal Saline</option>
              <option value={FluidType.HALF_NS}>1/2 Normal Saline</option>
              <option value={FluidType.COLLOID_ALBUMIN}>Albumin 5%</option>
              <option value={FluidType.PRBC}>Packed Red Blood Cells</option>
            </select>
          </div>

          <div className="space-y-2">
            <div className="flex justify-between text-sm">
               <label className="text-slate-400 font-bold">Volume</label>
               <span className="text-blue-400 font-mono">{volume} ml ({Math.round(volume/patient.weight_kg)} ml/kg)</span>
            </div>
            <input 
              type="range" 
              min={Math.round(patient.weight_kg * 5)} 
              max={Math.round(patient.weight_kg * 60)} 
              step={10}
              value={volume} 
              onChange={(e) => setVolume(Number(e.target.value))}
              className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
            />
          </div>

          <div className="space-y-2">
            <div className="flex justify-between text-sm">
               <label className="text-slate-400 font-bold">Duration</label>
               <span className="text-blue-400 font-mono">{duration} mins</span>
            </div>
             <input 
              type="range" min="5" max="240" step="5"
              value={duration} 
              onChange={(e) => setDuration(Number(e.target.value))}
              className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
            />
          </div>

          <button 
            onClick={handleSimulate}
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-4 rounded-lg flex justify-center items-center gap-2 transition-all active:scale-95 disabled:opacity-50"
          >
            {loading ? <span className="animate-spin h-5 w-5 border-2 border-white/30 border-t-white rounded-full"></span> : <><Play className="w-4 h-4 fill-current" /> Run Simulation</>}
          </button>
        </div>

        {/* RESULTS */}
        <div className="lg:col-span-8 p-6 bg-slate-900 min-h-[400px]">
          {result ? (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
              <div className="grid grid-cols-2 gap-4">
                 <div className="bg-slate-800 p-3 rounded border border-slate-700">
                    <div className="text-xs text-slate-500 uppercase">BP Response</div>
                    <div className={clsx("text-xl font-bold", result.summary.bp_end > result.summary.bp_start ? "text-emerald-400" : "text-slate-400")}>
                       {result.summary.bp_start} <span className="text-sm text-slate-500">→</span> {result.summary.bp_end} <span className="text-xs text-slate-500">mmHg</span>
                    </div>
                 </div>
                 <div className="bg-slate-800 p-3 rounded border border-slate-700">
                    <div className="text-xs text-slate-500 uppercase">Safety Check</div>
                    <div className={clsx("text-sm font-bold mt-1", result.summary.safety_alerts.length > 0 ? "text-red-400" : "text-emerald-400")}>
                       {result.summary.safety_alerts.length > 0 ? result.summary.safety_alerts[0] : "✅ Safe Protocol"}
                    </div>
                 </div>
              </div>

              <div className="bg-white rounded-xl p-1 overflow-hidden">
                 <TrajectoryChart data={result.graph_data} />
              </div>

              <div className="opacity-90 hover:opacity-100 transition-opacity">
                 <TankVisualizer data={{
                    trajectory: result.graph_data,
                    alerts: mapAlertsToFlags(result.summary.safety_alerts),
                    recommended_fluid: fluid as any,
                    bolus_volume_ml: volume,
                    infusion_duration_min: duration,
                    flow_rate_ml_hr: 0, drops_per_minute: 0, seconds_per_drop: 0, 
                    iv_set_used: '', max_safe_infusion_rate_ml_hr: 0, max_allowed_bolus_volume_ml: 0,
                    predicted_bp_rise: 0, stop_trigger_heart_rate: 0, stop_trigger_respiratory_rate: 0,
                    human_readable_summary: '', generated_at: ''
                 }} />
              </div>
            </div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-slate-600 space-y-4">
              <RotateCcw className="w-12 h-12 opacity-20" />
              <p>Adjust parameters and click Run to simulate.</p>
            </div>
          )}
        </div>

      </div>
    </div>
  );
};
