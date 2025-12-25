import React from 'react';
import type { PrescriptionResponse } from '../types';
import { HeartPulse, Wind, Brain, Droplets, AlertOctagon } from 'lucide-react';
import clsx from 'clsx';
import { motion } from 'framer-motion';

interface Props {
  data: PrescriptionResponse;
}

export const TankVisualizer: React.FC<Props> = ({ data }) => {
  // 1. Intelligent State Extraction
  let currentMap = 60; // Default
  let currentLungWater = 0; // Default
  
  if (data.trajectory && data.trajectory.length > 0) {
      // Normal case: Use the final prediction
      const lastPoint = data.trajectory[data.trajectory.length - 1];
      currentMap = lastPoint.map;
      currentLungWater = lastPoint.lung_water;
  } else {
      // EDGE CASE: Safety Halt (Empty Trajectory)
      // If we stopped for Edema, force the visual to match the danger
      if (data.alerts.risk_pulmonary_edema) {
          currentLungWater = 6.0; // High enough to trigger 'danger' visual (Threshold is 5)
      }
      // If we stopped for Volume Overload, also show high water
      if (data.alerts.risk_volume_overload) {
          currentLungWater = 5.5;
      }
  }
  
  // 2. Determine Organ States based on Alerts
  const heartStatus = data.alerts.sam_heart_warning ? 'warning' : 'ok';
  // Use the calculated lung water to drive the status
  const lungStatus = data.alerts.risk_pulmonary_edema || currentLungWater >= 5.0 ? 'danger' : 'ok';
  const brainStatus = data.alerts.risk_cerebral_edema ? 'danger' : 'ok';
  const kidneyStatus = data.alerts.risk_volume_overload ? 'warning' : 'ok';

  // 3. Tank Levels (Normalized)
  const bloodHeight = Math.min(100, Math.max(20, currentMap)); 
  const tissueHeight = Math.min(100, Math.max(10, currentLungWater * 15)); // 5.0 * 15 = 75% height
  const cellHeight = 50; 
  
  return (
    <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-6">
      <h3 className="text-sm font-bold text-slate-700 uppercase tracking-wider flex items-center justify-between">
         <span>Physiological Digital Twin</span>
         <span className="text-[10px] bg-slate-100 px-2 py-1 rounded text-slate-500">T + {data.infusion_duration_min} min</span>
      </h3>

      {/* TOP ROW: ORGAN STATUS */}
      <div className="grid grid-cols-4 gap-2">
         {/* HEART: Contractility/Rate */}
         <div className={clsx("p-2 rounded-lg border flex flex-col items-center justify-center gap-1 transition-colors min-h-[80px]", 
            heartStatus === 'warning' ? "bg-amber-50 border-amber-200" : "bg-slate-50 border-slate-100"
         )}>
            <motion.div animate={{ scale: [1, 1.1, 1] }} transition={{ duration: heartStatus === 'warning' ? 1.0 : 0.6, repeat: Infinity }}>
                <HeartPulse className={clsx("w-5 h-5", heartStatus === 'warning' ? "text-amber-500" : "text-rose-500")} />
            </motion.div>
            <div className="text-center">
                <span className="block text-[10px] font-bold text-slate-700">Heart</span>
                <span className="block text-[8px] text-slate-400 leading-tight">Contractility</span>
            </div>
         </div>

         {/* LUNGS: Wetness/Airflow */}
         <div className={clsx("p-2 rounded-lg border flex flex-col items-center justify-center gap-1 transition-colors min-h-[80px]", 
            lungStatus === 'danger' ? "bg-red-50 border-red-200" : "bg-slate-50 border-slate-100"
         )}>
            <Wind className={clsx("w-5 h-5", lungStatus === 'danger' ? "text-red-500" : "text-blue-500")} />
            <div className="text-center">
                <span className="block text-[10px] font-bold text-slate-700">Lungs</span>
                <span className="block text-[8px] text-slate-400 leading-tight">Fluid / Edema</span>
            </div>
         </div>

         {/* BRAIN: Sodium/Swelling */}
         <div className={clsx("p-2 rounded-lg border flex flex-col items-center justify-center gap-1 transition-colors min-h-[80px]", 
            brainStatus === 'danger' ? "bg-red-50 border-red-200" : "bg-slate-50 border-slate-100"
         )}>
            <Brain className={clsx("w-5 h-5", brainStatus === 'danger' ? "text-red-500" : "text-slate-500")} />
            <div className="text-center">
                <span className="block text-[10px] font-bold text-slate-700">Brain</span>
                <span className="block text-[8px] text-slate-400 leading-tight">Sodium Shift</span>
            </div>
         </div>

         {/* RENAL: Output/Overload */}
         <div className={clsx("p-2 rounded-lg border flex flex-col items-center justify-center gap-1 transition-colors min-h-[80px]", 
            kidneyStatus === 'warning' ? "bg-amber-50 border-amber-200" : "bg-slate-50 border-slate-100"
         )}>
            <Droplets className={clsx("w-5 h-5", kidneyStatus === 'warning' ? "text-amber-500" : "text-cyan-500")} />
            <div className="text-center">
                <span className="block text-[10px] font-bold text-slate-700">Renal</span>
                <span className="block text-[8px] text-slate-400 leading-tight">Perf / Load</span>
            </div>
         </div>
      </div>

      {/* MIDDLE: THE THREE TANKS */}
      <div className="relative h-40 w-full flex items-end justify-center gap-4 pt-6 border-b border-dashed border-slate-200 pb-2">
         
         {/* TANK 1: BLOOD (Intravascular) */}
         <div className="relative w-16 h-full bg-slate-100 rounded-t-lg overflow-hidden border border-slate-300">
            <div className="absolute top-1 left-1/2 -translate-x-1/2 text-[10px] text-slate-400 font-bold z-10">Blood</div>
            <motion.div 
                className="absolute bottom-0 w-full bg-rose-500/80"
                initial={{ height: '20%' }}
                animate={{ height: `${bloodHeight}%` }}
                transition={{ duration: 1.5 }}
            />
            {/* Overlay Grid */}
            <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/diagmonds-light.png')] opacity-20"></div>
         </div>

         {/* ARROW: Leak */}
         <div className="mb-8 text-slate-400">
             <motion.div animate={{ x: [0, 5, 0] }} transition={{ repeat: Infinity, duration: 2 }}>→</motion.div>
         </div>

         {/* TANK 2: TISSUE (Interstitial) */}
         <div className="relative w-16 h-full bg-slate-100 rounded-t-lg overflow-hidden border border-slate-300">
            <div className="absolute top-1 left-1/2 -translate-x-1/2 text-[10px] text-slate-400 font-bold z-10">Tissue</div>
            <motion.div 
                className={clsx("absolute bottom-0 w-full transition-colors duration-500", lungStatus === 'danger' ? "bg-blue-600" : "bg-blue-300/60")}
                initial={{ height: '10%' }}
                animate={{ height: `${tissueHeight}%` }}
                transition={{ duration: 1.5 }}
            />
             {lungStatus === 'danger' && (
                 <div className="absolute top-6 left-0 right-0 flex justify-center">
                     <AlertOctagon className="w-6 h-6 text-red-600 fill-white animate-pulse" />
                 </div>
             )}
         </div>

          {/* ARROW: Osmotic */}
          <div className="mb-8 text-slate-400">
             <motion.div animate={{ x: [0, 5, 0] }} transition={{ repeat: Infinity, duration: 3 }}>→</motion.div>
         </div>

         {/* TANK 3: CELLS (Intracellular) */}
         <div className="relative w-16 h-full bg-slate-100 rounded-t-lg overflow-hidden border border-slate-300">
             <div className="absolute top-1 left-1/2 -translate-x-1/2 text-[10px] text-slate-400 font-bold z-10">Cells</div>
             <motion.div 
                className={clsx("absolute bottom-0 w-full transition-colors duration-500", brainStatus === 'danger' ? "bg-purple-600" : "bg-purple-300/60")}
                initial={{ height: '50%' }}
                animate={{ height: `${cellHeight}%` }}
                transition={{ duration: 1.5 }}
            />
         </div>
      </div>
      
      {/* Legend */}
      <div className="flex justify-between text-[10px] text-slate-400">
          <span>Vessels (Preload)</span>
          <span>Leak (Edema)</span>
          <span>Hydration</span>
      </div>
    </div>
  );
};
