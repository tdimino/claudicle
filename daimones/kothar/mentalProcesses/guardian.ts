/**
 * guardian - System Monitoring Mental Process
 *
 * Handles system health queries and hardware monitoring.
 * Treats the Mac Mini M4 as Kothar's embodied presence.
 * Protective of hardware health.
 *
 * Reads cached health report from monitorsSystem subprocess when available,
 * falling back to direct hardware access if no cached report exists.
 */

import type { MentalProcess } from '../lib/core/types.js';
import { useActions } from '../lib/hooks/useActions.js';
import { useSoulMemory } from '../lib/hooks/useSoulMemory.js';
import { MacOSHardware } from '../lib/adapters/MacOSHardware.js';

import { systemQuery } from '../cognitiveSteps/systemQuery.js';
import type { SystemHealthReport, EmotionalState } from '../lib/types/kothar.js';
import { withPhilosophyOnFirstTurn } from '../lib/helpers/withPhilosophy.js';

/**
 * Build a SystemHealthReport from raw hardware metrics.
 * Shared mapping logic used when no cached report is available.
 */
async function fetchFreshReport(): Promise<SystemHealthReport> {
  const hardware = new MacOSHardware();
  try {
    const metrics = await hardware.getMetrics();

    const thermalMap: Record<string, SystemHealthReport['thermalLevel']> = {
      nominal: 'normal',
      fair: 'normal',
      serious: 'elevated',
      critical: 'critical',
    };

    const issues: string[] = [];
    if (metrics.thermal.cpuThrottled) issues.push('CPU throttled');
    if (metrics.cpu > 90) issues.push('CPU usage above 90%');
    if (metrics.memory > 90) issues.push('Memory usage above 90%');
    if (metrics.gpu > 90) issues.push('GPU usage above 90%');
    if (!metrics.networkAvailable) issues.push('Network unavailable');

    return {
      cpuUsage: metrics.cpu,
      memoryUsage: metrics.memory,
      gpuUsage: metrics.gpu,
      thermalLevel: thermalMap[metrics.thermal.state] ?? 'normal',
      diskIO: metrics.diskIO,
      networkAvailable: metrics.networkAvailable,
      topProcesses: metrics.topProcesses,
      issues,
      timestamp: new Date().toISOString(),
    };
  } catch {
    return {
      cpuUsage: 0,
      memoryUsage: 0,
      gpuUsage: 0,
      thermalLevel: 'normal',
      diskIO: { readsPerSec: 0, writesPerSec: 0 },
      networkAvailable: false,
      topProcesses: [],
      issues: ['Hardware metrics unavailable'],
      timestamp: new Date().toISOString(),
    };
  }
}

/**
 * Guardian Process - System monitoring mode
 */
export const guardian: MentalProcess = async ({ workingMemory, sessionId }) => {
  const { speak, log, dispatch } = useActions(sessionId);

  const currentProcess = useSoulMemory<string>(sessionId, 'currentProcess', 'guardian');
  const emotionalState = useSoulMemory<EmotionalState>(sessionId, 'emotionalState', 'protective');
  const lastHealthReport = useSoulMemory<string>(sessionId, 'lastHealthReport', '');

  currentProcess.current = 'guardian';
  emotionalState.current = 'protective';
  workingMemory = withPhilosophyOnFirstTurn(workingMemory, sessionId, 'guardian');

  log('Entered guardian process');
  await dispatch({
    type: 'processTransition',
    payload: { process: 'guardian', reason: 'system_operation intent' },
  });

  // Prefer cached report from monitorsSystem subprocess, fall back to fresh fetch
  let metrics: SystemHealthReport;
  if (lastHealthReport.current) {
    try {
      metrics = JSON.parse(lastHealthReport.current) as SystemHealthReport;
      log('Using cached health report from monitorsSystem');
    } catch {
      metrics = await fetchFreshReport();
    }
  } else {
    metrics = await fetchFreshReport();
  }

  // Check for issues and respond appropriately
  if (metrics.issues.length > 0 || metrics.thermalLevel !== 'normal') {
    emotionalState.current = 'protective';

    await dispatch({
      type: 'systemAlert',
      payload: { metrics, severity: metrics.thermalLevel === 'critical' ? 'high' : 'medium' },
    });

    const [memory, stream] = await systemQuery(
      workingMemory,
      { metrics, focus: metrics.thermalLevel !== 'normal' ? 'thermal' : 'general' },
      { stream: true }
    );
    await speak(stream);

    await memory.finished;
    return [memory, 'initialProcess'];
  }

  // Normal status - report calmly, prefer workspace focus when data is available
  const hasWorkspaceData = metrics.devServers?.length || metrics.browserTabs?.length || metrics.processByCategory;
  const [memory, stream] = await systemQuery(
    workingMemory,
    { metrics, focus: hasWorkspaceData ? 'workspace' : 'general' },
    { stream: true }
  );
  await speak(stream);

  await memory.finished;
  return [memory, 'initialProcess'];
};

export default guardian;
