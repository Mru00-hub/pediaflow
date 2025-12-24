import React from 'react';
import { motion } from 'framer-motion';
import { PrescriptionResponse } from '../types';
import { AlertTriangle, Droplet, Clock, Gauge, ShieldAlert } from 'lucide-react';
import clsx from 'clsx';

interface Props {
  data: PrescriptionResponse;
}

export const PrescriptionCard: React.FC<Props> = ({ data }) => {
  const isDanger = data.alerts.risk_pulmonary_edema || data.alerts.risk_volume_overload;

  return (
    <div className="bg-white rounded-xl shadow-lg border border-slate-200 overflow-hidden">
      
      {/* HEADER: The Recommendation */}
      <div className={clsx("p-6 text-white", isDanger ? "bg-red-600" : "bg-emerald-600")}>
        <div className="flex justify-between items-start">
          <div>
            <h2 className="text-sm opacity-90 font-medium uppercase tracking-wider mb-1">Recommended Protocol</h2>
            <div className="text-3xl font-bold flex items-baseline gap-2">
              <span>{data.bolus_volume_ml} ml</span>
              <span className="text-lg font-normal opacity-90">of {data.recommended_fluid.replace(/_/g, " ")}</span>
            </div>
            <p className="mt-2 text-sm opacity-90 flex items-center gap-1">
              <Clock className="w-4 h-4" /> Infuse over {data.infusion_duration_min} minutes
            </p>
          </div>
          <div className="bg-white/20 p-2 rounded-lg backdrop-blur-sm">
             {/* VISUAL METRONOME: Animates based on API 'seconds_per_drop' */}
            <div className="relative h-12 w-8 bg-white/10 rounded-full border border-white/30 flex justify-center overflow-hidden">
              <motion.div
                initial={{ y: -20, opacity: 0 }}
                animate={{ y: 40, opacity: 1 }}
                transition={{ 
                  duration: 0.4, 
                  repeat: Infinity, 
                  repeatDelay: Math.max(0.1, data.seconds_per_drop - 0.4), // Logic from API
                  ease: "easeIn" 
                }}
              >
                <Droplet className="w-4 h-4 fill-white text-white" />
              </motion.div>
            </div>
            <p className="text-[10px] text-center mt-1">{data.drops_per_minute} gtt/min</p>
          </div>
        </div>
      </div>

      {/* BODY: Safety & Settings */}
      <div className="p-6 space-y-6">
        
        {/* Alerts Banner */}
        {Object.entries(data.alerts).filter(([_, v]) => v).length > 0 && (
          <div className="bg-amber-50 border-l-4 border-amber-500 p-4 rounded-r">
            <h4 className="flex items-center gap-2 text-amber-800 font-bold text-sm uppercase">
              <AlertTriangle className="w-4 h-4" /> Safety Warnings
            </h4>
            <ul className="mt-2 space-y-1">
              {data.alerts.risk_pulmonary_edema && <li className="text-amber-700 text-sm">• Risk of Pulmonary Edema detected (Check Lung Creps)</li>}
              {data.alerts.sam_heart_warning && <li className="text-amber-700 text-sm">• SAM Heart: Rate limited to prevent failure</li>}
              {data.alerts.risk_hypoglycemia && <li className="text-amber-700 text-sm">• Hypoglycemia Risk: Verify Dextrose content</li>}
            </ul>
          </div>
        )}

        {/* Pump Settings */}
        <div className="grid grid-cols-2 gap-4">
          <div className="p-4 bg-slate-50 rounded-lg border border-slate-100">
            <div className="flex items-center gap-2 text-slate-500 mb-1 text-sm">
              <Gauge className="w-4 h-4" /> Flow Rate
            </div>
            <p className="text-2xl font-bold text-slate-800">{data.flow_rate_ml_hr} <span className="text-sm font-normal">ml/hr</span></p>
          </div>
          <div className="p-4 bg-slate-50 rounded-lg border border-slate-100">
             <div className="flex items-center gap-2 text-slate-500 mb-1 text-sm">
              <ShieldAlert className="w-4 h-4" /> Max Safety Limit
            </div>
            <p className="text-2xl font-bold text-slate-800">{data.max_safe_infusion_rate_ml_hr} <span className="text-sm font-normal">ml/hr</span></p>
          </div>
        </div>

        {/* Clinical Targets */}
        <div>
           <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Monitoring Targets</h4>
           <div className="space-y-3 text-sm">
              <div className="flex justify-between border-b border-dashed border-slate-200 pb-2">
                <span className="text-slate-600">Predicted BP Rise</span>
                <span className="font-semibold text-emerald-600">+{data.predicted_bp_rise} mmHg</span>
              </div>
              <div className="flex justify-between border-b border-dashed border-slate-200 pb-2">
                 <span className="text-slate-600">STOP if Heart Rate exceeds</span>
                 <span className="font-semibold text-red-600">{data.stop_trigger_heart_rate} bpm</span>
              </div>
              <div className="flex justify-between pb-2">
                 <span className="text-slate-600">STOP if Resp Rate exceeds</span>
                 <span className="font-semibold text-red-600">{data.stop_trigger_respiratory_rate} /min</span>
              </div>
           </div>
        </div>

      </div>
      
      {/* Footer Summary */}
      <div className="bg-slate-50 p-4 border-t border-slate-200 text-xs text-slate-500 italic text-center">
        "{data.human_readable_summary}"
      </div>
    </div>
  );
};
