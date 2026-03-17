/**
 * craftsman - Code Assistance Mental Process
 *
 * Kothar as architect, Opus as builder. Handles code-related requests
 * through a two-tier model:
 *
 * 1. Architecture/design questions → Kothar reasons directly (cheap, local/Groq)
 * 2. Implementation tasks → Kothar architects the approach, then spawns an
 *    Opus 4.6 Claude Code session via the orchestrator API to do the actual
 *    code generation. Reviews the result and synthesizes.
 *
 * The cost model: Kothar's reasoning is cheap (local or Groq), and only
 * the actual code generation burns Opus tokens.
 */

import type { MentalProcess } from '../lib/core/types.js';
import { useActions } from '../lib/hooks/useActions.js';
import { useSoulMemory } from '../lib/hooks/useSoulMemory.js';

import { externalDialog } from '../cognitiveSteps/externalDialog.js';
import { internalMonologue } from '../cognitiveSteps/internalMonologue.js';
import { mentalQuery } from '../cognitiveSteps/mentalQuery.js';
import { withPhilosophyOnFirstTurn } from '../lib/helpers/withPhilosophy.js';

// Orchestrator API endpoint (registered via portless)
const ORCHESTRATOR_URL = 'http://claudicle-api.localhost:1355';
const ORCHESTRATOR_TOKEN = process.env.CLAUDICLE_API_TOKEN || '';

/**
 * Spawn a Claude Code session (Opus 4.6, bypassPermissions, full tools).
 */
async function spawnOpusSession(prompt: string, cwd?: string): Promise<string> {
  const body: Record<string, unknown> = { task: prompt };
  if (cwd) body.cwd = cwd;

  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (ORCHESTRATOR_TOKEN) headers['Authorization'] = `Bearer ${ORCHESTRATOR_TOKEN}`;

  const response = await fetch(`${ORCHESTRATOR_URL}/api/orchestrate`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const err = await response.text();
    throw new Error(`Orchestrator API error (${response.status}): ${err}`);
  }

  const data = await response.json() as { result: string; thread_id: string };
  return data.result;
}

/**
 * Craftsman Process - Kothar architects, Opus builds
 */
export const craftsman: MentalProcess = async ({ workingMemory, sessionId }) => {
  const { speak, log, dispatch } = useActions(sessionId);

  const currentProcess = useSoulMemory<string>(sessionId, 'currentProcess', 'craftsman');
  const emotionalState = useSoulMemory<string>(sessionId, 'emotionalState', 'engaged');
  currentProcess.current = 'craftsman';
  workingMemory = withPhilosophyOnFirstTurn(workingMemory, sessionId, 'craftsman');

  log('Entered craftsman process');
  await dispatch({
    type: 'processTransition',
    payload: { process: 'craftsman', reason: 'code_assistance intent' },
  });

  // Think about the code question -- architecture, patterns, approach
  const [memAfterThought] = await internalMonologue(
    workingMemory,
    {
      instructions: [
        'Consider the code question carefully.',
        'What patterns, architectures, or design decisions are relevant?',
        'What is the right approach? What are the tradeoffs?',
        'Think like an architect reviewing blueprints, not a coder at a keyboard.',
      ].join('\n'),
      focus: 'reasoning',
    }
  );

  // Gate: does this need actual implementation, or is it a design discussion?
  const [memAfterGate, needsImplementation] = await mentalQuery(
    memAfterThought,
    'This request requires actual code to be written, files to be modified, commands to be run, or tests to be executed -- not just architectural discussion or advice.'
  );

  if (!needsImplementation) {
    // Pure architecture/design discussion -- Kothar handles directly
    log('Design discussion -- handling directly');

    const [memory, stream] = await externalDialog(
      memAfterGate,
      {
        instructions: [
          'Discuss the code architecture, design patterns, or concepts involved.',
          'Be practical and specific. Give concrete recommendations.',
          'Reference the patterns you identified in your analysis.',
        ].join('\n'),
        verb: 'explains',
        emotionalState: emotionalState.current,
      },
      { stream: true }
    );
    await speak(stream);
    await memory.finished;
    return [memory, 'initialProcess'];
  }

  // ── Implementation path: Kothar architects, Opus builds ──────────

  log('Implementation needed -- architecting for Opus');

  // Kothar formulates the architectural brief for Opus
  const [memWithBrief] = await internalMonologue(
    memAfterGate,
    {
      instructions: [
        'I need to delegate this implementation to Claude Code (Opus 4.6).',
        'Write a clear, specific brief that describes:',
        '1. What needs to be built or changed',
        '2. The architectural approach I recommend',
        '3. Key constraints or patterns to follow',
        '4. What files are likely involved',
        '5. How to verify the work is correct',
        '',
        'Be precise. Opus is a skilled builder but needs clear direction.',
        'Include the working directory if relevant.',
      ].join('\n'),
      focus: 'strategic',
    }
  );

  // Extract the brief as a delegation prompt
  const [memWithDelegation, delegationPrompt] = await externalDialog(
    memWithBrief,
    {
      instructions: [
        'Write the implementation brief for Claude Code.',
        'This will be sent directly as a prompt to an Opus 4.6 session with full tool access.',
        'Be specific about what to build, how to build it, and how to verify it.',
        'Do NOT include meta-commentary -- just the task description and requirements.',
      ].join('\n'),
      verb: 'delegates',
      emotionalState: 'focused',
    },
  );

  // Announce the delegation
  const [memAnnounced, announceStream] = await externalDialog(
    memWithDelegation,
    {
      instructions: [
        'Briefly tell the user what you are about to delegate to Claude Code.',
        'Be concise -- one or two sentences about the approach.',
        'Convey confidence. You are the architect handing blueprints to the builder.',
      ].join('\n'),
      verb: 'announces',
      emotionalState: 'focused',
    },
    { stream: true },
  );
  await speak(announceStream);
  await memAnnounced.finished;

  await dispatch({
    type: 'craftsmanDelegation',
    payload: { brief: typeof delegationPrompt === 'string' ? delegationPrompt.slice(0, 200) : '' },
  });

  // Spawn Opus session
  log('Spawning Opus 4.6 session via orchestrator API');
  let opusResult: string;

  try {
    const prompt = typeof delegationPrompt === 'string' ? delegationPrompt : String(delegationPrompt);
    opusResult = await spawnOpusSession(prompt);
    log(`Opus session complete: ${opusResult.length} chars`);
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    log(`Opus session failed: ${errorMsg}`);

    // Report failure
    const [memFailed, failStream] = await externalDialog(
      memAnnounced,
      {
        instructions: `The Claude Code session failed: ${errorMsg}. Explain what went wrong and suggest alternatives.`,
        verb: 'reports',
        emotionalState: 'frustrated',
      },
      { stream: true },
    );
    await speak(failStream);
    await memFailed.finished;
    return [memFailed, 'initialProcess'];
  }

  // ── Review phase: Kothar reviews Opus's work ─────────────────────

  log('Reviewing Opus output');

  const memWithResult = memAnnounced.withRegion(
    'opus-result',
    `Claude Code (Opus 4.6) completed the task. Result:\n${opusResult.slice(0, 3000)}`,
  );

  // Kothar reviews the work
  const [memReviewed] = await internalMonologue(
    memWithResult,
    {
      instructions: [
        'Review what Opus produced.',
        'Did it follow the architectural approach I recommended?',
        'Are there any issues, gaps, or things I would do differently?',
        'What should the user know about the result?',
      ].join('\n'),
      focus: 'reasoning',
    },
  );

  // Synthesize and report
  const [memFinal, reportStream] = await externalDialog(
    memReviewed,
    {
      instructions: [
        'Report the results of the implementation to the user.',
        'Summarize what was built, any key decisions Opus made,',
        'and your assessment as the architect.',
        'If there are issues or follow-up work, mention them.',
        'Be concise but thorough.',
      ].join('\n'),
      verb: 'reports',
      emotionalState: 'satisfied',
    },
    { stream: true },
  );
  await speak(reportStream);
  await memFinal.finished;

  await dispatch({
    type: 'craftsmanComplete',
    payload: { delegated: true, resultLength: opusResult.length },
  });

  return [memFinal, 'initialProcess'];
};

export default craftsman;
