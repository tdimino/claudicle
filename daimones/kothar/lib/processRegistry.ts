/**
 * Process Registry - Kothar Soul Process Loader
 *
 * Maps process names to dynamic imports, following the Open Souls
 * per-soul processRegistry pattern. Resolves string-based process
 * identifiers at runtime, eliminating circular imports.
 *
 * Mental processes return string names:
 *   return [memory, 'initialProcess']
 *
 * The ProcessRunner resolves them via loadProcess().
 */

import type { MentalProcess } from './core/types.js';

/**
 * All registered process names for this soul
 */
export const PROCESS_NAMES = [
  'initialProcess',
  'craftsman',
  'scholar',
  'guardian',
  'outraged',
  'surrealistDream',
  'dreamReflection',
  'herald',
  'orchestrator',
] as const;

export type ProcessName = (typeof PROCESS_NAMES)[number];

/**
 * Process cache to avoid re-importing
 */
const processCache = new Map<string, MentalProcess>();

/**
 * Load a mental process by name using dynamic imports.
 * Caches the result for subsequent calls.
 */
export async function loadProcess(processName: string): Promise<MentalProcess | null> {
  // Return cached if available
  if (processCache.has(processName)) {
    return processCache.get(processName)!;
  }

  let process: MentalProcess | null = null;

  // Dynamic imports — each case is an explicit static string for bundler compatibility
  switch (processName) {
    case 'initialProcess':
      process = (await import('../mentalProcesses/initialProcess.js')).default;
      break;
    case 'craftsman':
      process = (await import('../mentalProcesses/craftsman.js')).default;
      break;
    case 'scholar':
      process = (await import('../mentalProcesses/scholar.js')).default;
      break;
    case 'guardian':
      process = (await import('../mentalProcesses/guardian.js')).default;
      break;
    case 'outraged':
      process = (await import('../mentalProcesses/outraged.js')).default;
      break;
    case 'surrealistDream':
      process = (await import('../mentalProcesses/surrealistDream.js')).default;
      break;
    case 'dreamReflection':
      process = (await import('../mentalProcesses/dreamReflection.js')).default;
      break;
    case 'herald':
      process = (await import('../mentalProcesses/herald.js')).default;
      break;
    case 'orchestrator':
      process = (await import('../mentalProcesses/orchestrator.js')).default;
      break;
    default:
      return null;
  }

  if (process) {
    processCache.set(processName, process);
  }
  return process;
}
