import React, { useState } from 'react';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, 
  ResponsiveContainer, ReferenceLine, Legend 
} from 'recharts';
import { AlertTriangle, Activity, FlaskConical, Droplet } from 'lucide-react';
import clsx from 'clsx';

interface Props {
  data: Array<{
    time: number;
    map: number;
    lung_water: number;
    leak_rate: number;
    hct: number;
    sodium: number;
    potassium: number;
    glucose: number;
    hb: number;
  }>;
}

export const TrajectoryChart: React.FC<Props> = ({ data }) => {
  // 1. Solution: Three distinct views to solve scaling issues
  const [view, setView] = useState<'hemo' | 'lytes' | 'metabolic'>('hemo');

  // Auto-scale Lung Water so the graph doesn't look empty if healthy
  // Default to 6 so the "Edema Threshold" (5) is always visible
  const maxLungWater = Math.max(...data.map(d => d.lung_water), 6);

  return (
    <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col h-full min-h-[350px]">
      
      {/* HEADER: Title + Tabs */}
      <div className="flex flex-col sm:flex-row justify-between items-center mb-4 gap-3 border-b border-slate-100 pb-3">
        <h3 className="text-sm font-bold text-slate-700 uppercase tracking-wider">
           60-Minute Forecast
        </h3>
        
        {/* Toggle Controls */}
        <div className="flex bg-slate-100 p-1 rounded-lg">
           <button 
             onClick={() => setView('hemo')}
             className={clsx("px-3 py-1 text-[10px] font-bold rounded-md flex items-center gap-1 transition-all", 
               view === 'hemo' ? "bg-white text-emerald-600 shadow-sm ring-1 ring-slate-200" : "text-slate-400 hover:text-slate-600"
             )}
           >
             <Activity className="w-3 h-3" /> Hemodynamics
           </button>
           <button 
             onClick={() => setView('lytes')}
             className={clsx("px-3 py-1 text-[10px] font-bold rounded-md flex items-center gap-1 transition-all", 
               view === 'lytes' ? "bg-white text-purple-600 shadow-sm ring-1 ring-slate-200" : "text-slate-400 hover:text-slate-600"
             )}
           >
             <FlaskConical className="w-3 h-3" /> Lytes
           </button>
           <button 
             onClick={() => setView('metabolic')}
             className={clsx("px-3 py-1 text-[10px] font-bold rounded-md flex items-center gap-1 transition-all", 
               view === 'metabolic' ? "bg-white text-amber-600 shadow-sm ring-1 ring-slate-200" : "text-slate-400 hover:text-slate-600"
             )}
           >
             <Droplet className="w-3 h-3" /> Metabolic
           </button>
        </div>
      </div>

      {/* CHART AREA - Fixed height to prevent "height(-1)" errors */}
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
            
            <XAxis 
                dataKey="time" 
                label={{ value: 'Time (min)', position: 'insideBottomRight', offset: -5, fontSize: 10 }} 
                tick={{ fontSize: 10, fill: '#64748b' }}
                axisLine={false}
                tickLine={false}
            />
            
            <Tooltip 
                contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)', fontSize: '12px' }}
                labelStyle={{ fontWeight: 'bold', color: '#64748b', marginBottom: '4px' }}
                formatter={(value: number) => [value, '']} 
            />
            <Legend wrapperStyle={{ paddingTop: '10px', fontSize: '11px' }} iconType="circle" />

            {/* --- VIEW 1: HEMODYNAMICS --- */}
            {view === 'hemo' && (
              <>
                <YAxis 
                    yAxisId="left" 
                    domain={[30, 100]} 
                    label={{ value: 'MAP (mmHg)', angle: -90, position: 'insideLeft', fontSize: 10, fill: '#10b981' }} 
                    tick={{ fontSize: 10, fill: '#10b981' }} 
                    width={40}
                />
                <YAxis 
                    yAxisId="right" 
                    orientation="right" 
                    domain={[0, maxLungWater]} 
                    label={{ value: 'Lung Water', angle: 90, position: 'insideRight', fontSize: 10, fill: '#3b82f6' }} 
                    tick={{ fontSize: 10, fill: '#3b82f6' }} 
                    width={40}
                />
                
                <ReferenceLine y={5.0} yAxisId="right" stroke="#ef4444" strokeDasharray="3 3" label={{ value: 'Edema', fill: 'red', fontSize: 10, position: 'insideTopRight' }} />

                <Line yAxisId="left" type="monotone" dataKey="map" stroke="#10b981" strokeWidth={2} dot={false} name="MAP (mmHg)" />
                <Line yAxisId="right" type="monotone" dataKey="lung_water" stroke="#3b82f6" strokeWidth={2} dot={false} name="Lung Water" />
              </>
            )}

            {/* --- VIEW 2: ELECTROLYTES --- */}
            {view === 'lytes' && (
              <>
                 <YAxis 
                    yAxisId="na" 
                    domain={['auto', 'auto']} 
                    label={{ value: 'Sodium', angle: -90, position: 'insideLeft', fontSize: 10, fill: '#8b5cf6' }}
                    tick={{ fontSize: 10, fill: '#8b5cf6' }} 
                    width={40}
                 />
                 <YAxis 
                    yAxisId="k" 
                    orientation="right" 
                    domain={[0, 8]} 
                    label={{ value: 'Potassium', angle: 90, position: 'insideRight', fontSize: 10, fill: '#f59e0b' }}
                    tick={{ fontSize: 10, fill: '#f59e0b' }} 
                    width={40}
                 />

                 <Line yAxisId="na" type="monotone" dataKey="sodium" stroke="#8b5cf6" strokeWidth={2} dot={false} name="Sodium (Na+)" />
                 <Line yAxisId="k" type="monotone" dataKey="potassium" stroke="#f59e0b" strokeWidth={2} dot={false} name="Potassium (K+)" />
                 
                 {/* Safety Thresholds */}
                 <ReferenceLine y={150} yAxisId="na" stroke="#ef4444" strokeDasharray="3 3" />
                 <ReferenceLine y={130} yAxisId="na" stroke="#ef4444" strokeDasharray="3 3" />
              </>
            )}

            {/* --- VIEW 3: METABOLIC --- */}
            {view === 'metabolic' && (
              <>
                 <YAxis 
                    yAxisId="gluc" 
                    domain={[0, 'auto']} 
                    label={{ value: 'Glucose', angle: -90, position: 'insideLeft', fontSize: 10, fill: '#f97316' }}
                    tick={{ fontSize: 10, fill: '#f97316' }} 
                    width={40}
                 />
                 <YAxis 
                    yAxisId="hb" 
                    orientation="right" 
                    domain={[0, 18]} 
                    label={{ value: 'Hb (g/dL)', angle: 90, position: 'insideRight', fontSize: 10, fill: '#ef4444' }}
                    tick={{ fontSize: 10, fill: '#ef4444' }} 
                    width={40}
                 />

                 <Line yAxisId="gluc" type="monotone" dataKey="glucose" stroke="#f97316" strokeWidth={2} dot={false} name="Glucose" />
                 <Line yAxisId="hb" type="monotone" dataKey="hb" stroke="#ef4444" strokeWidth={2} strokeDasharray="5 5" dot={false} name="Hemoglobin" />
                 
                 <ReferenceLine y={7.0} yAxisId="hb" stroke="#ef4444" strokeDasharray="3 3" label={{ value: 'Transfuse', fill: 'red', fontSize: 10 }} />
              </>
            )}

          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-4 flex items-start gap-2 text-xs text-slate-400 bg-slate-50 p-2 rounded border border-slate-100">
         <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0" />
         <p>Model assumes no further intervention after initial bolus. Re-assess clinical signs every 15 mins.</p>
      </div>
    </div>
  );
};
