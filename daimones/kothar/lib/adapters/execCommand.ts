/**
 * execCommand - Shell command helper for subprocesses.
 *
 * Wraps child_process.exec with timeout and error swallowing.
 * Used by monitorsSystem to call portless, cdp.mjs, syspeek.
 */

import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

/**
 * Execute a shell command and return stdout. Returns empty string on failure.
 */
export async function execCommand(cmd: string, timeoutMs = 5000): Promise<string> {
  try {
    const { stdout } = await execAsync(cmd, { timeout: timeoutMs });
    return stdout.trim();
  } catch {
    return '';
  }
}
