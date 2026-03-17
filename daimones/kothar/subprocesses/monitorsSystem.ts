/**
 * monitorsSystem - Hardware Health Monitoring Subprocess
 *
 * Monitors system health and sets emotional state to 'protective'
 * when issues are detected. Runs alongside main processes.
 * Does NOT speak to the user directly.
 *
 * Rate-limited: checks hardware at most every 5 minutes to avoid
 * unnecessary overhead from frequent polling.
 */

import type { MentalProcess } from '../lib/core/types.js';
import { ChatMessageRoleEnum } from '../lib/core/types.js';
import { useActions } from '../lib/hooks/useActions.js';
import { useSoulMemory } from '../lib/hooks/useSoulMemory.js';
import { MacOSHardware } from '../lib/adapters/MacOSHardware.js';
import { execCommand } from '../lib/adapters/execCommand.js';
import type { EmotionalState, SystemHealthReport } from '../lib/types/kothar.js';

/** Minimum interval between health checks (5 minutes) */
const CHECK_INTERVAL_MS = 5 * 60 * 1000;

/**
 * Parse `portless list` output into structured dev server entries.
 * Format: "  http://name.localhost:1355  ->  localhost:4469  (pid 57331)"
 */
function parsePortlessList(output: string): NonNullable<SystemHealthReport['devServers']> {
  const servers: NonNullable<SystemHealthReport['devServers']> = [];
  for (const line of output.split('\n')) {
    const match = line.match(/^\s+(https?:\/\/\S+)\s+->\s+\S+\s+\(pid\s+(\d+)\)/);
    if (match) {
      const url = match[1];
      const pid = parseInt(match[2], 10);
      const name = url.replace(/https?:\/\//, '').replace(/\.localhost:\d+$/, '');
      servers.push({ name, url, pid });
    }
  }
  return servers;
}

/**
 * Parse `cdp.mjs list` output into browser tab entries.
 * Only includes localhost tabs (dev server previews).
 */
function parseCdpList(output: string): NonNullable<SystemHealthReport['browserTabs']> {
  const tabs: NonNullable<SystemHealthReport['browserTabs']> = [];
  for (const line of output.split('\n')) {
    if (!line.includes('localhost')) continue;
    const parts = line.trim().split(/\s+/);
    if (parts.length >= 2) {
      const id = parts[0];
      const url = parts.find(p => p.startsWith('http')) || parts[1];
      const title = parts.slice(parts.indexOf(url) + 1).join(' ') || url;
      tabs.push({ id, title, url });
    }
  }
  return tabs;
}

/**
 * Parse `syspeek --json` output into categorized process summary.
 * Syspeek returns: { categories: { "Claude Code": { count, total_cpu, total_mem }, ... } }
 */
function parseSyspeekCategories(output: string): SystemHealthReport['processByCategory'] {
  try {
    const data = JSON.parse(output);
    const categories = data.categories || data;
    const result: NonNullable<SystemHealthReport['processByCategory']> = {};
    for (const [name, info] of Object.entries(categories)) {
      const cat = info as Record<string, number>;
      result[name] = {
        count: cat.count ?? 0,
        totalCpu: cat.total_cpu ?? cat.totalCpu ?? 0,
        totalMem: cat.total_mem ?? cat.totalMem ?? 0,
      };
    }
    return Object.keys(result).length > 0 ? result : undefined;
  } catch {
    return undefined;
  }
}

/**
 * monitorsSystem - Subprocess that watches hardware health
 */
export const monitorsSystem: MentalProcess = async ({ workingMemory, sessionId }) => {
  const { log, dispatch } = useActions(sessionId);

  const emotionalState = useSoulMemory<EmotionalState>(sessionId, 'emotionalState', 'neutral');
  const lastHealthCheck = useSoulMemory<number>(sessionId, 'lastHealthCheck', 0);
  const lastHealthReport = useSoulMemory<string>(sessionId, 'lastHealthReport', '');

  const now = Date.now();
  const elapsed = now - lastHealthCheck.current;

  // Rate limit: skip if checked recently
  if (elapsed < CHECK_INTERVAL_MS) {
    log(`System monitor: skipping (last check ${Math.round(elapsed / 1000)}s ago)`);
    return workingMemory;
  }

  log('System monitor: running health check');
  lastHealthCheck.current = now;

  // Fetch hardware metrics
  const hardware = new MacOSHardware();
  let report: SystemHealthReport;

  try {
    const metrics = await hardware.getMetrics();

    // Map thermal state to our levels
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
    if (!metrics.power.onACPower) issues.push('Not on AC power');
    if (!metrics.networkAvailable) issues.push('Network unavailable');

    report = {
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
  } catch (error) {
    log('System monitor: hardware adapter unavailable');
    report = {
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

  // ── Workspace environment data ──────────────────────────────────
  // Each call is independent and failure-tolerant.
  // Subprocess pattern: collect data silently, persist via useSoulMemory.

  // Portless: active dev servers
  const portlessOut = await execCommand('portless list');
  if (portlessOut && !portlessOut.includes('No active')) {
    const servers = parsePortlessList(portlessOut);
    if (servers.length > 0) {
      report.devServers = servers;
      log(`Workspace: ${servers.length} dev server(s) active`);
    }
  }

  // Chrome CDP: open browser tabs on localhost
  const cdpOut = await execCommand('node ~/.claude/skills/chrome-cdp/scripts/cdp.mjs list');
  if (cdpOut) {
    const tabs = parseCdpList(cdpOut);
    if (tabs.length > 0) {
      report.browserTabs = tabs;
      log(`Workspace: ${tabs.length} browser tab(s) on localhost`);
    }
  }

  // Syspeek: categorized process view
  const syspeekOut = await execCommand('python3 ~/.claude/scripts/syspeek/syspeek.py --json');
  if (syspeekOut) {
    const categories = parseSyspeekCategories(syspeekOut);
    if (categories) {
      report.processByCategory = categories;
      log(`Workspace: ${Object.keys(categories).length} process categories`);
    }
  }

  // Workspace-specific issue detection
  if (report.devServers && report.devServers.length > 0 && !report.browserTabs?.length) {
    report.issues.push('Dev server running but no browser tabs open');
  }
  const mlCategory = report.processByCategory?.['ML'];
  if (mlCategory && mlCategory.totalMem > 50) {
    report.issues.push(`ML processes using ${mlCategory.totalMem.toFixed(0)}% memory`);
  }
  const tabCount = report.browserTabs?.length ?? 0;
  if (tabCount > 20) {
    report.issues.push(`${tabCount} Chrome tabs open — consider closing unused tabs`);
  }

  // Store the report
  lastHealthReport.current = JSON.stringify(report);

  // Evaluate whether to shift emotional state
  const hasIssues = report.issues.length > 0 && !report.issues.includes('Hardware metrics unavailable');
  const isThermalConcern = report.thermalLevel !== 'normal';

  if (hasIssues || isThermalConcern) {
    log('System monitor: issues detected', report.issues);

    // Only shift to protective if not already in a stronger state (outraged)
    if (emotionalState.current !== 'outraged') {
      emotionalState.current = 'protective';
    }

    const severity = report.thermalLevel === 'critical' ? 'high' : 'medium';

    await dispatch({
      type: 'systemAlert',
      payload: { report, severity },
    });

    // Add concern to working memory so main process can reference it
    return workingMemory.withMemory({
      role: ChatMessageRoleEnum.System,
      content: `System health concern: ${report.issues.join(', ')}. Thermal: ${report.thermalLevel}.`,
      region: 'system-health',
      metadata: { type: 'systemHealth', report },
    });
  }

  log('System monitor: all healthy');
  return workingMemory;
};

export default monitorsSystem;
