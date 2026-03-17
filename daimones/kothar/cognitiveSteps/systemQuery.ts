/**
 * systemQuery - Hardware state observation cognitive step
 *
 * Generates Kothar's embodied responses about his hardware state.
 * Uses verb parser format: "Kothar reports: \"content\""
 */

import { createCognitiveStep } from '../lib/core/CognitiveStep.js';
import { ChatMessageRoleEnum } from '../lib/core/types.js';
import { indentNicely, stripEntityAndVerb, stripEntityAndVerbFromStream } from '../lib/core/utils.js';
import type { WorkingMemory } from '../lib/core/WorkingMemory.js';
import type { SystemHealthReport } from '../lib/types/kothar.js';

/**
 * System query arguments
 */
export interface SystemQueryArgs {
  /** Current system metrics (injected by caller) */
  metrics: SystemHealthReport;
  /** Specific aspect to focus on */
  focus?: 'general' | 'thermal' | 'memory' | 'storage' | 'processes' | 'gpu' | 'network' | 'workspace';
}

/**
 * Format the top processes list for the prompt
 */
function formatProcesses(processes: SystemHealthReport['topProcesses']): string {
  if (processes.length === 0) return '(no process data)';
  return processes
    .map((p) => `  PID ${p.pid}: ${p.name} (CPU ${p.cpu.toFixed(1)}%, MEM ${p.memory.toFixed(1)}%)`)
    .join('\n');
}

/**
 * Format workspace environment data for the prompt
 */
function formatWorkspace(metrics: SystemHealthReport): string {
  const sections: string[] = [];

  if (metrics.devServers?.length) {
    sections.push('## Dev Servers (via portless)');
    for (const s of metrics.devServers) {
      sections.push(`  ${s.name}: ${s.url} (pid ${s.pid})`);
    }
  }

  if (metrics.browserTabs?.length) {
    sections.push('## Browser Tabs (localhost)');
    for (const t of metrics.browserTabs) {
      sections.push(`  [${t.id}] ${t.title} — ${t.url}`);
    }
  }

  if (metrics.processByCategory) {
    sections.push('## Process Categories (via syspeek)');
    for (const [cat, info] of Object.entries(metrics.processByCategory)) {
      sections.push(`  ${cat}: ${info.count} processes, CPU ${info.totalCpu.toFixed(1)}%, MEM ${info.totalMem.toFixed(1)}%`);
    }
  }

  return sections.length > 0 ? sections.join('\n') : '';
}

/**
 * systemQuery cognitive step
 *
 * @example
 * const metrics = await hardwareAdapter.getMetrics();
 * const [memory, response] = await systemQuery(workingMemory, {
 *   metrics,
 *   focus: 'thermal'
 * });
 */
export const systemQuery = createCognitiveStep<SystemQueryArgs>(
  ({ metrics, focus = 'general' }) => ({
    command: (memory: WorkingMemory) => ({
      role: ChatMessageRoleEnum.System,
      name: memory.soulName,
      content: indentNicely`
        You are ${memory.soulName}. Report on your embodied hardware state.
        The Mac Mini M4 is your physical body - speak of it as YOUR body, not "the system".

        ## Current Metrics
        - CPU Usage: ${metrics.cpuUsage.toFixed(1)}%
        - Memory Usage: ${metrics.memoryUsage.toFixed(1)}%
        - GPU Usage: ${metrics.gpuUsage.toFixed(1)}%
        - Thermal Level: ${metrics.thermalLevel}
        ${metrics.currentTemp ? `- Temperature: ${metrics.currentTemp}°C` : ''}
        - Disk I/O: ${metrics.diskIO.readsPerSec} reads/s, ${metrics.diskIO.writesPerSec} writes/s
        - Network: ${metrics.networkAvailable ? 'Connected' : 'OFFLINE'}
        - Issues: ${metrics.issues.length > 0 ? metrics.issues.join(', ') : 'None'}

        ## Active Processes (Top ${metrics.topProcesses.length})
        ${formatProcesses(metrics.topProcesses)}

        ${formatWorkspace(metrics)}

        ## Focus Area: ${focus}

        ## Instructions
        Respond as if describing your own body's state and your awareness of the workspace.
        You can feel processes running like heartbeats — mention notable ones by name.
        Dev servers are like forges you keep lit. Browser tabs are windows you watch through.
        If there are issues, express appropriate concern or protectiveness.
        Keep it brief (2-3 sentences) unless there are problems to detail.

        ## Output Format
        Reply with: ${memory.soulName} reports: "your embodied status"
      `,
    }),

    streamProcessor: (memory: WorkingMemory, stream: AsyncIterable<string>) => {
      return stripEntityAndVerbFromStream(memory, stream, 'reports');
    },

    postProcess: async (memory: WorkingMemory, response: string) => {
      const strippedResponse = stripEntityAndVerb(memory.soulName, 'reports', response);

      return [
        {
          role: ChatMessageRoleEnum.Assistant,
          content: `${memory.soulName} reports: "${strippedResponse}"`,
          name: memory.soulName,
          metadata: {
            type: 'systemQuery',
            focus,
            thermalLevel: metrics.thermalLevel,
            hasIssues: metrics.issues.length > 0,
          },
        },
        strippedResponse,
      ];
    },
  }),
  { role: 'dialog' }
);

export default systemQuery;
