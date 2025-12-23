# app.py
from models import (
    PatientInput, EngineOutput, ValidationResult, FluidType
)
from core_physics import PediaFlowPhysicsEngine
from protocols import FluidSelector, PrescriptionEngine
from safety import SafetySupervisor

# --- METADATA & COMPLIANCE ---
__version__ = "1.0.0"
__model_date__ = "2025-12-22"
__validation_status__ = "Clinical validation pending"
__iap_guideline_version = "IAP 2023 Shock Guidelines"
__who_fluid_version = "WHO 2022 Pocketbook"

MEDICAL_DISCLAIMER = """
⚠️ DECISION SUPPORT TOOL - NOT A PRESCRIPTION
• Final responsibility: Treating physician
• Not a substitute for clinical judgment
• Offline calculator - no real-time monitoring
"""

def generate_prescription(data: dict) -> EngineOutput:
    """
    Main Orchestrator:
    1. Validates Input -> Creates Digital Twin
    2. Selects Protocol-based Fluid
    3. Calculates Dosage & Drip Rates
    4. Runs Kinetic Simulation (Safety Check)
    5. Returns Clinical Instructions
    """
    
    # 1. Create Twin
    # This validates the dictionary against PatientInput rules
    twin: ValidationResult = PediaFlowPhysicsEngine.create_digital_twin(data)
    
    if not twin.success:
        # In a real API, you might raise an HTTP exception here.
        # For the engine, we propagate the error.
        raise ValueError(f"Digital Twin Creation Failed: {twin.errors}")

    # 2. Select Fluid
    # Uses IAP/WHO logic (e.g. Sepsis -> RL, Hypoglycemia -> D5)
    fluid = FluidSelector.select_initial_fluid(twin.patient, twin.initial_state)
    
    # 3. Calculate Dose
    # Calculates volume and physical hardware settings (drops/min)
    rx = PrescriptionEngine.generate_bolus(twin.patient, fluid)
    
    # 4. Simulate
    # Fast-forward time to check for edema/overload risks
    sim_res = PediaFlowPhysicsEngine.run_simulation(
        twin.initial_state, twin.physics_params, fluid, 
        rx['volume_ml'], rx['duration_min']
    )
    
    # 5. Check Safety
    # Analyze the final state of the simulation for physiological limits
    alerts = SafetySupervisor.check_real_time(
        sim_res['final_state'], twin.physics_params, twin.patient
    )
    
    # 6. Construct Human Readable Summary
    summary = (
        f"Give {rx['volume_ml']}ml of {fluid.value.replace('_', ' ').title()} "
        f"over {rx['duration_min']} mins. "
        f"Set rate to {rx['rate_ml_hr']} ml/hr ({rx['drops_per_min']} drops/min)."
    )

    # 7. Return Result
    # Maps all the internal physics numbers to the strict output schema
    return EngineOutput(
        recommended_fluid=fluid,
        bolus_volume_ml=rx['volume_ml'],
        infusion_duration_min=rx['duration_min'],
        
        # Hardware Instructions
        iv_set_used=twin.patient.iv_set_available.name.replace("_", " ").title(),
        flow_rate_ml_hr=rx['rate_ml_hr'],
        drops_per_minute=rx['drops_per_min'],
        seconds_per_drop=rx['seconds_per_drop'],
        
        # Predictions & Triggers
        predicted_bp_rise=sim_res['predicted_map_rise'],
        stop_trigger_heart_rate=twin.physics_params.target_heart_rate_upper_limit,
        stop_trigger_respiratory_rate=twin.physics_params.target_respiratory_rate_limit,
        stop_trigger_liver_span_increase=True, # Standard shock protocol trigger
        
        # Hard Safety Limits
        # Max safe rate is generally capped at 2x the calculated bolus rate for pump safety
        max_safe_infusion_rate_ml_hr=int(rx['rate_ml_hr'] * 1.5), 
        # Standard safety cap for a single bolus is 20ml/kg
        max_allowed_bolus_volume_ml=int(twin.patient.weight_kg * 20), 
        
        # Clinical Context Flags
        requires_glucose=(fluid == FluidType.D5_NS),
        requires_blood=(fluid == FluidType.PRBC),
        
        alerts=alerts,
        human_readable_summary=summary
    )
