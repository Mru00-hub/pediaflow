import React from 'react';
import { motion } from 'framer-motion';
import type { PrescriptionResponse, SafetyAlerts } from '../types';
import { 
  AlertTriangle, 
  Droplet, 
  Clock, 
  Gauge, 
  ShieldAlert, 
  Hand, 
  Activity, 
  HeartPulse 
} from 'lucide-react';
import clsx from 'clsx';

interface Props {
  data: PrescriptionResponse;
}

// 1. Map ALL backend alerts to human-readable strings
const ALERT_MESSAGES: Partial<Record<keyof SafetyAlerts, string>> = {
  risk_pulmonary_edema: "Risk of Pulmonary Edema (Check Creps)",
  risk_volume_overload: "Volume Overload Risk (> Safe Limit)",
  risk_cerebral_edema: "Cerebral Edema Risk (Rapid Sodium Shift)",
  risk_hypoglycemia: "Hypoglycemia Risk: Verify Dextrose Content",
  hydrocortisone_needed: "Refractory Shock: Consider Hydrocortisone",
  risk_ketoacidosis: "Ketoacidosis Risk: Check Ketones/ABG",
  sam_heart_warning: "SAM Heart: Infusion Rate Capped",
  anemia_dilution_warning: "Critical Anemia: Hemodilution Risk",
  dengue_leak_warning: "Active Dengue Capillary Leak Detected"
};

export const PrescriptionCard: React.FC<Props> = ({ data }) => {
  // 2. Dynamic Danger Check: If ANY alert is active, turn header red
  const activeAlerts = Object.entries(data.alerts)
    .filter(([key, isActive]) => isActive && key in ALERT_MESSAGES);
  
  const isDanger = activeAlerts.length > 0;

  // 3. Helper to format "ringer_lactate" -> "Ringer Lactate"
  const fluidName = data.recommended_fluid
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');

  return (
    <div className="bg-white rounded-xl shadow-lg border border-slate-200 overflow-hidden flex flex-col h-full">
      
      {/* HEADER: The Recommendation */}
      <div className={clsx("p-6 text-white transition-colors duration-300", isDanger ? "bg-red-600" : "bg-emerald-600")}>
        <div className="flex justify-between items-start">
          <div>
            <h2 className="text-xs opacity-80 font-bold uppercase tracking-widest mb-1">Recommended Protocol</h2>
            <div className="text-4xl font-extrabold flex items-baseline gap-2">
              <span>{data.bolus_volume_ml}<span className="text-2xl ml-1">ml</span></span>
            </div>
            <div className="text-lg font-medium opacity-95 mt-1">{fluidName}</div>
            
            <p className="mt-3 text-sm opacity-90 flex items-center gap-2 bg-black/10 w-fit px-3 py-1 rounded-full">
              <Clock className="w-3.5 h-3.5" /> 
              <span>Over <strong>{data.infusion_duration_min}</strong> minutes</span>
            </p>
          </div>

          {/* VISUAL METRONOME */}
          <div className="bg-white/20 p-3 rounded-xl backdrop-blur-md border border-white/20 flex flex-col items-center min-w-[80px]">
            <div className="relative h-14 w-8 bg-black/20 rounded-full border border-white/30 flex justify-center overflow-hidden shadow-inner">
              {/* Only animate if rate is reasonable (<100 dpm). If uncountable, show static stream */}
              {data.drops_per_minute < 100 ? (
                <motion.div
                    initial={{ y: -20, opacity: 0 }}
                    animate={{ y: 45, opacity: 1 }}
                    transition={{ 
                    duration: 0.4, 
                    repeat: Infinity, 
                    // Ensure visual separation even at high rates
                    repeatDelay: Math.max(0.2, data.seconds_per_drop - 0.4), 
                    ease: "easeIn" 
                    }}
                >
                    <Droplet className="w-4 h-4 fill-white text-white" />
                </motion.div>
              ) : (
                  <div className="w-1 h-full bg-white/60 animate-pulse" /> // Static stream for high rates
              )}
            </div>
            <p className="text-[10px] font-bold text-center mt-2 leading-tight">
                {data.drops_per_minute > 100 ? '>100' : data.drops_per_minute}<br/>gtt/min
            </p>
          </div>
        </div>
      </div>

      {/* BODY: Safety & Settings */}
      <div className="p-6 space-y-6 flex-grow">
        
        {/* Dynamic Alerts Banner */}
        {activeAlerts.length > 0 && (
          <div className="bg-amber-50 border-l-4 border-amber-500 p-4 rounded-r-md shadow-sm">
            <h4 className="flex items-center gap-2 text-amber-800 font-bold text-xs uppercase tracking-wider">
              <AlertTriangle className="w-4 h-4" /> Safety Warnings
            </h4>
            <ul className="mt-2 space-y-1.5">
              {activeAlerts.map(([key, _]) => (
                <li key={key} className="text-amber-900 text-sm font-medium flex items-start gap-2">
                    <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-amber-500 flex-shrink-0" />
                    {ALERT_MESSAGES[key as keyof SafetyAlerts]}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Pump Settings */}
        <div className="grid grid-cols-2 gap-4">
          <div className="p-4 bg-slate-50 rounded-xl border border-slate-100 flex flex-col justify-between">
            <div className="flex items-center gap-2 text-slate-500 mb-1 text-xs font-bold uppercase tracking-wider">
              <Gauge className="w-4 h-4" /> Flow Rate
            </div>
            <p className="text-2xl font-bold text-slate-800 tracking-tight">
                {data.flow_rate_ml_hr} 
                <span className="text-sm font-medium text-slate-400 ml-1">ml/hr</span>
            </p>
          </div>
          <div className="p-4 bg-slate-50 rounded-xl border border-slate-100 flex flex-col justify-between">
             <div className="flex items-center gap-2 text-slate-500 mb-1 text-xs font-bold uppercase tracking-wider">
              <ShieldAlert className="w-4 h-4" /> Max Limit
            </div>
            <p className="text-2xl font-bold text-slate-800 tracking-tight">
                {data.max_safe_infusion_rate_ml_hr} 
                <span className="text-sm font-medium text-slate-400 ml-1">ml/hr</span>
            </p>
          </div>
        </div>

        {/* Monitoring Targets (High Contrast) */}
        <div>
           <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Clinical Targets</h4>
           <div className="space-y-4">
              
              {/* BP Target */}
              <div className="flex justify-between items-center pb-3 border-b border-slate-100">
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-emerald-100 rounded-lg text-emerald-600">
                        <Activity className="w-4 h-4" />
                    </div>
                    <span className="text-sm font-medium text-slate-700">Expected MAP Rise</span>
                </div>
                <span className="font-bold text-emerald-600 text-lg">+{data.predicted_bp_rise} <span className="text-xs">mmHg</span></span>
              </div>

              {/* Heart Rate Stop Trigger */}
              <div className="flex justify-between items-center pb-3 border-b border-slate-100">
                 <div className="flex items-center gap-3">
                    <div className="p-2 bg-rose-100 rounded-lg text-rose-600">
                        <Hand className="w-4 h-4" />
                    </div>
                    <div className="flex flex-col">
                        <span className="text-sm font-bold text-slate-700">STOP Infusion</span>
                        <span className="text-xs text-slate-400">If Heart Rate Exceeds</span>
                    </div>
                 </div>
                 <span className="font-bold text-rose-600 text-lg">{data.stop_trigger_heart_rate} <span className="text-xs">bpm</span></span>
              </div>

              {/* RR Stop Trigger */}
              <div className="flex justify-between items-center">
                 <div className="flex items-center gap-3">
                    <div className="p-2 bg-rose-100 rounded-lg text-rose-600">
                        <Hand className="w-4 h-4" />
                    </div>
                    <div className="flex flex-col">
                        <span className="text-sm font-bold text-slate-700">STOP Infusion</span>
                        <span className="text-xs text-slate-400">If Resp Rate Exceeds</span>
                    </div>
                 </div>
                 <span className="font-bold text-rose-600 text-lg">{data.stop_trigger_respiratory_rate} <span className="text-xs">/min</span></span>
              </div>

           </div>
        </div>
      </div>
      
      {/* Footer Summary */}
      <div className="bg-slate-50 p-4 border-t border-slate-200 text-xs text-slate-500 text-center font-medium">
        "{data.human_readable_summary}"
      </div>
    </div>
  );
};
