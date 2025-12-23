# safety.py
from models import SimulationState, PhysiologicalParams, PatientInput, SafetyAlerts

class SafetySupervisor:
    @staticmethod
    def check_real_time(state: SimulationState, params: PhysiologicalParams, 
                        input: PatientInput) -> SafetyAlerts:
        alerts = SafetyAlerts()
        
        # Cerebral Edema (Na change > 12 mEq/24h)
        time_hours = state.time_minutes / 60.0
        if time_hours > 0:
            na_rate = state.total_sodium_load_meq / time_hours
            if na_rate * 24 > 12.0:
                alerts.risk_cerebral_edema = True
        
        # Hypoglycemia
        if state.current_glucose_mg_dl < 54.0:
            alerts.risk_hypoglycemia = True
        
        # SAM Heart Warning
        if params.cardiac_contractility < 0.6:
            alerts.sam_heart_warning = True
            
        return alerts
