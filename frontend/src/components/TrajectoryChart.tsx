import React from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine } from 'recharts';
import { AlertTriangle } from 'lucide-react';

interface Props {
  data: Array<{
    time: number;
    map: number;
    lung_water: number;
    leak_rate: number;
    hct: number;
  }>;
}

export const TrajectoryChart: React.FC<Props> = ({ data }) => {
  // Calculate max lung water to auto-scale the graph if it gets dangerous
  const maxLungWater = Math.max(...data.map(d => d.lung_water), 6);

  return (
    <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-sm font-bold text-slate-700 uppercase tracking-wider">
           60-Minute Prediction Model
        </h3>
        <div className="flex gap-4 text-xs">
             <div className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-emerald-500"></span> Mean Arterial Pressure (BP)
             </div>
             <div className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-blue-500"></span> Lung Water (Edema)
             </div>
        </div>
      </div>

      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
            <XAxis 
                dataKey="time" 
                label={{ value: 'Time (min)', position: 'insideBottomRight', offset: -5 }} 
                tick={{ fontSize: 12 }}
            />
            
            {/* Left Axis: Blood Pressure */}
            <YAxis 
                yAxisId="left" 
                domain={[30, 100]} 
                label={{ value: 'MAP (mmHg)', angle: -90, position: 'insideLeft' }} 
                tick={{ fontSize: 12, fill: '#10b981' }}
            />
            
            {/* Right Axis: Lung Water */}
            <YAxis 
                yAxisId="right" 
                orientation="right" 
                domain={[0, maxLungWater]} 
                label={{ value: 'Lung Water (mmHg)', angle: 90, position: 'insideRight' }} 
                tick={{ fontSize: 12, fill: '#3b82f6' }}
            />
            
            <Tooltip 
                contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                labelStyle={{ fontWeight: 'bold', color: '#64748b' }}
            />
            
            {/* The Safe Limit Line for Lung Water */}
            <ReferenceLine y={5.0} yAxisId="right" stroke="#ef4444" strokeDasharray="3 3" label={{ value: 'Edema Threshold', fill: 'red', fontSize: 10 }} />

            <Line 
                yAxisId="left"
                type="monotone" 
                dataKey="map" 
                stroke="#10b981" 
                strokeWidth={2} 
                dot={false} 
                name="MAP (mmHg)"
            />
            <Line 
                yAxisId="right"
                type="monotone" 
                dataKey="lung_water" 
                stroke="#3b82f6" 
                strokeWidth={2} 
                dot={false} 
                name="Lung Water (mmHg)"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-2 flex items-start gap-2 text-xs text-slate-400 bg-slate-50 p-2 rounded">
         <AlertTriangle className="w-3 h-3 mt-0.5" />
         <p>Model assumes no intervention after bolus. Re-assess clinical signs every 15 mins.</p>
      </div>
    </div>
  );
};
