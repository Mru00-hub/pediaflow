// api.ts
import { PatientInput, PrescriptionResponse, SimulationRequest, SimulationResponse } from './types';

// Default to localhost for development
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

class PediaFlowClient {
  
  /**
   * Helper to handle fetch responses and error parsing
   */
  private async handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      // Throw the specific "Clinical Validation Error" if available
      throw new Error(errorData.detail || `API Error: ${response.statusText}`);
    }
    return response.json();
  }

  /**
   * POST /prescribe
   * Generates the fluid resuscitation plan.
   */
  async getPrescription(patient: PatientInput): Promise<PrescriptionResponse> {
    const response = await fetch(`${API_BASE_URL}/prescribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patient),
    });
    return this.handleResponse<PrescriptionResponse>(response);
  }

  /**
   * POST /simulate
   * Runs the "What-If" prediction scenario.
   */
  async runSimulation(payload: SimulationRequest): Promise<SimulationResponse> {
    const response = await fetch(`${API_BASE_URL}/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return this.handleResponse<SimulationResponse>(response);
  }
}

export const api = new PediaFlowClient();
