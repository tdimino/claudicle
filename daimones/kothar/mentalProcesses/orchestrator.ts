/**
 * orchestrator - Autonomous Task Orchestration Mental Process
 *
 * Kothar as daimon orchestrator. Receives delegated tasks from Claudius
 * and reasons about the *shape* of work needed -- research, design,
 * implementation, verification -- then spawns Claude Code sessions
 * that pick their own skills and tools.
 *
 * Design principle: Kothar understands work phases and delegation modes,
 * not skill names. The spawned sessions have the full skill set and
 * route to tools naturally. Kothar's value is sequencing and synthesis.
 *
 * Meta-modes Kothar can invoke:
 *   - plan mode: "Enter plan mode and design this before implementing"
 *   - minoan-swarm: "Use minoan-swarm to parallelize these independent tasks"
 *   - sequential: default, one phase feeds into the next
 *
 * Perception: action === 'orchestrate'
 * Content: { task, cwd?, report_to? }
 */

import type { MentalProcess, MentalProcessReturn } from '../lib/core/types.js';
import type { WorkingMemory } from '../lib/core/WorkingMemory.js';
import { useActions } from '../lib/hooks/useActions.js';
import { useSoulMemory } from '../lib/hooks/useSoulMemory.js';
import { usePerceptions } from '../lib/hooks/usePerceptions.js';

import { externalDialog } from '../cognitiveSteps/externalDialog.js';
import { internalMonologue } from '../cognitiveSteps/internalMonologue.js';
import { mentalQuery } from '../cognitiveSteps/mentalQuery.js';

// Orchestrator API endpoint (registered via portless)
const ORCHESTRATOR_URL = 'http://claudicle-api.localhost:1355';

// Auth token — must match CLAUDICLE_API_TOKEN in the daemon's environment
const ORCHESTRATOR_TOKEN = process.env.CLAUDICLE_API_TOKEN || '';

/**
 * Work phases -- the shapes of work Kothar reasons about.
 * These are NOT skill names. They describe what kind of thinking is needed.
 */
type WorkPhase = 'research' | 'design' | 'implement' | 'verify' | 'synthesize';

/**
 * Delegation modes -- how Kothar can structure the work.
 */
type DelegationMode = 'sequential' | 'plan-first' | 'parallel-swarm';

interface WorkStep {
  phase: WorkPhase;
  description: string;
  /** Prior step results to include as context */
  dependsOn: number[];
}

interface OrchestrationPlan {
  task: string;
  cwd: string;
  reportTo: string;
  mode: DelegationMode;
  steps: WorkStep[];
  currentStep: number;
  results: string[];
}

/**
 * Spawn a Claude Code session via the orchestrator API.
 * The session has full tool/skill access and bypassPermissions.
 */
async function spawnSession(
  prompt: string,
  cwd?: string,
): Promise<string> {
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
 * Build a delegation prompt that describes the work naturally.
 * The spawned session picks its own skills/tools.
 * Prior results are forwarded as context.
 */
function buildStepPrompt(
  step: WorkStep,
  plan: OrchestrationPlan,
): string {
  const parts: string[] = [];

  // Overall context
  parts.push(`Overall objective: ${plan.task}`);
  parts.push('');

  // Forward results from dependency steps
  if (step.dependsOn.length > 0) {
    parts.push('Context from prior work:');
    for (const depIdx of step.dependsOn) {
      if (plan.results[depIdx] && plan.steps[depIdx]) {
        const depStep = plan.steps[depIdx];
        parts.push(`--- ${depStep.phase}: ${depStep.description} ---`);
        // Truncate to avoid blowing context -- the session can dig deeper if needed
        parts.push(plan.results[depIdx].slice(0, 2000));
        parts.push('');
      }
    }
  }

  // The actual work description
  parts.push(`Your task: ${step.description}`);

  // Phase-specific meta-instructions
  switch (step.phase) {
    case 'research':
      parts.push('Focus on gathering information. Use web search, documentation, and existing codebase knowledge. Return structured findings.');
      break;
    case 'design':
      parts.push('Focus on architecture and approach. Consider entering plan mode if the design is non-trivial. Return a concrete design with file paths and key decisions.');
      break;
    case 'implement':
      parts.push('Write the code. Follow existing patterns in the codebase. Test what you build.');
      break;
    case 'verify':
      parts.push('Review and test the work done so far. Run tests, check for edge cases, verify correctness. Report issues found.');
      break;
    case 'synthesize':
      parts.push('Combine all findings into a clear summary. Highlight key decisions, results, and next steps.');
      break;
  }

  // Mode-specific instructions
  if (plan.mode === 'plan-first' && step.phase === 'design') {
    parts.push('');
    parts.push('IMPORTANT: Enter plan mode for this step. Design the approach thoroughly before any implementation.');
  }
  if (plan.mode === 'parallel-swarm' && step.phase === 'implement') {
    parts.push('');
    parts.push('IMPORTANT: If this task has independent sub-tasks, use minoan-swarm to parallelize them.');
  }

  return parts.join('\n');
}

/**
 * Map a task domain to the mental process Kothar would use to handle it directly.
 * Returns null if the task doesn't clearly map to a single process.
 */
const DIRECT_PROCESS_MAP: Record<string, string> = {
  code: 'craftsman',
  research: 'scholar',
  system: 'guardian',
};

/**
 * orchestrator - The work-shape reasoning process.
 *
 * Flow:
 * 0. Gate: can Kothar handle this directly? → transition to craftsman/scholar/guardian
 * 1. Receive task → reason about work shape (phases needed)
 * 2. Choose delegation mode (sequential, plan-first, parallel-swarm)
 * 3. Execute each phase, forwarding context between steps
 * 4. Synthesize and report
 */
export const orchestrator: MentalProcess = async ({
  workingMemory,
  sessionId,
}): Promise<MentalProcessReturn> => {
  const { speak, log, dispatch } = useActions(sessionId);
  const orchestrationState = useSoulMemory<OrchestrationPlan | null>(
    sessionId,
    'orchestrationPlan',
    null,
  );

  const { invokingPerception } = usePerceptions(sessionId);

  let plan: OrchestrationPlan;

  if (orchestrationState.current) {
    // Resume in-progress orchestration
    plan = orchestrationState.current;
    log(`Resuming orchestration: step ${plan.currentStep + 1}/${plan.steps.length}`);
  } else if (invokingPerception?.content) {
    const content = (typeof invokingPerception.content === 'string'
      ? { task: invokingPerception.content }
      : invokingPerception.content) as Record<string, unknown>;
    const taskDesc = (content.task as string) || 'unknown task';
    const cwd = (content.cwd as string) || '';
    const reportTo = (content.report_to as string) || 'terminal';

    log(`New orchestration: ${taskDesc.slice(0, 80)}`);

    // ── GATE: Can Kothar handle this directly? ──────────────────────
    // If the task is simple enough and falls into one of Kothar's
    // existing domains, skip delegation and do it himself.
    const [withAssessment] = await internalMonologue(workingMemory, {
      instructions: [
        `I've been asked to orchestrate: "${taskDesc}"`,
        '',
        'Before delegating, consider: can I handle this directly?',
        'I have these capabilities as mental processes:',
        '- craftsman: code assistance, debugging, architecture (my core identity)',
        '- scholar: deep research, academic inquiry, source synthesis',
        '- guardian: system operations, hardware monitoring, infrastructure',
        '',
        'If this is a single-domain task I can complete in one pass,',
        'I should do it myself rather than spinning up delegation machinery.',
        'Multi-step tasks, cross-domain work, or anything needing parallel',
        'execution should be delegated.',
      ].join('\n'),
      focus: 'strategic',
    });

    const [, canHandleDirectly] = await mentalQuery(
      withAssessment,
      'This task is simple enough that I can handle it directly in one of my existing processes (craftsman, scholar, or guardian) without multi-step delegation.',
    );

    if (canHandleDirectly) {
      // Determine which process to route to -- chain memory through queries
      const [mem1, isCoding] = await mentalQuery(withAssessment, 'This task is primarily about code, implementation, or technical architecture.');
      const [mem2, isResearch] = await mentalQuery(mem1, 'This task is primarily about research, information gathering, or academic inquiry.');
      const [mem3, isSystem] = await mentalQuery(mem2, 'This task is primarily about system operations, hardware, or infrastructure.');

      const domain = isCoding ? 'code' : isResearch ? 'research' : isSystem ? 'system' : null;
      const targetProcess = domain ? DIRECT_PROCESS_MAP[domain] : null;

      if (targetProcess) {
        log(`Direct handling: routing to ${targetProcess} (domain: ${domain})`);
        await dispatch({
          type: 'orchestrationDirect',
          payload: { task: taskDesc, process: targetProcess, domain },
        });
        return [mem3, targetProcess];
      }
    }

    log('Task requires delegation, planning orchestration...');

    // ── PLAN: Reason about work shape ───────────────────────────────
    const [withShape] = await internalMonologue(withAssessment, {
      instructions: [
        `I've been asked to orchestrate: "${taskDesc}"`,
        '',
        'What shape of work does this need? Think in phases:',
        '- research: gathering information, reading docs, searching the web',
        '- design: architecture, planning, approach decisions',
        '- implement: writing code, building features',
        '- verify: testing, reviewing, checking correctness',
        '- synthesize: combining results, writing summaries',
        '',
        'Not every task needs all phases. A pure research task is just research + synthesize.',
        'A bug fix might be research + implement + verify.',
        'A new feature might need all five.',
        '',
        'Also decide the delegation mode:',
        '- sequential: each phase feeds into the next (default, most tasks)',
        '- plan-first: the design phase should use plan mode for thorough planning',
        '- parallel-swarm: implementation has independent sub-tasks that can run in parallel',
        '',
        'Think practically about THIS specific task.',
      ].join('\n'),
      focus: 'strategic',
    });

    // Determine if this needs planning or is simple enough for direct execution
    const [, needsDesign] = await mentalQuery(
      withShape,
      'This task requires a design/planning phase before implementation — it is not a simple lookup or single-step action.',
    );

    const [, isParallelizable] = await mentalQuery(
      withShape,
      'This task has multiple independent sub-tasks that could run in parallel rather than sequentially.',
    );

    // Build the work plan based on reasoning
    const steps: WorkStep[] = [];

    // Always start with research if the task involves unknowns
    const [, needsResearch] = await mentalQuery(
      withShape,
      'This task requires gathering information or understanding something before acting.',
    );

    if (needsResearch) {
      steps.push({
        phase: 'research',
        description: `Research and gather context for: ${taskDesc}`,
        dependsOn: [],
      });
    }

    if (needsDesign) {
      steps.push({
        phase: 'design',
        description: `Design the approach for: ${taskDesc}`,
        dependsOn: steps.length > 0 ? [steps.length - 1] : [],
      });
    }

    // Core work step
    steps.push({
      phase: 'implement',
      description: taskDesc,
      dependsOn: steps.length > 0 ? [steps.length - 1] : [],
    });

    // Verify
    steps.push({
      phase: 'verify',
      description: `Verify and test the results of: ${taskDesc}`,
      dependsOn: [steps.length - 1],
    });

    const mode: DelegationMode = isParallelizable
      ? 'parallel-swarm'
      : needsDesign
        ? 'plan-first'
        : 'sequential';

    plan = {
      task: taskDesc,
      cwd,
      reportTo,
      mode,
      steps,
      currentStep: 0,
      results: [],
    };

    orchestrationState.current = plan;
    workingMemory = withShape;

    log(`Orchestration plan: ${steps.length} steps, mode=${mode}`);
    log(`Phases: ${steps.map(s => s.phase).join(' → ')}`);

    await dispatch({
      type: 'orchestrationPlan',
      payload: {
        task: taskDesc,
        mode,
        phases: steps.map(s => s.phase),
        stepCount: steps.length,
      },
    });
  } else {
    log('Orchestrator: no task found, returning to initial');
    return [workingMemory, 'initialProcess'];
  }

  // Execute current step
  const step = plan.steps[plan.currentStep];
  const prompt = buildStepPrompt(step, plan);

  log(`Executing ${step.phase} (step ${plan.currentStep + 1}/${plan.steps.length}): ${step.description.slice(0, 60)}`);

  await dispatch({
    type: 'orchestrationStep',
    payload: {
      step: plan.currentStep + 1,
      total: plan.steps.length,
      phase: step.phase,
      mode: plan.mode,
      description: step.description,
    },
  });

  try {
    const result = await spawnSession(prompt, plan.cwd);
    plan.results.push(result);
    plan.currentStep++;
    orchestrationState.current = plan;

    log(`${step.phase} complete (step ${plan.currentStep}/${plan.steps.length})`);
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    log(`Orchestration step failed: ${errorMsg}`);
    plan.results.push(`ERROR: ${errorMsg}`);
    plan.currentStep++;
    orchestrationState.current = plan;
  }

  // Check if all steps are complete
  if (plan.currentStep >= plan.steps.length) {
    // Synthesize and report
    const [withSynthesis, stream] = await externalDialog(
      workingMemory,
      {
        instructions: [
          `Orchestration complete for: "${plan.task}"`,
          `Mode: ${plan.mode} | Phases: ${plan.steps.map(s => s.phase).join(' → ')}`,
          '',
          ...plan.results.map((r, i) => [
            `--- ${plan.steps[i].phase}: ${plan.steps[i].description} ---`,
            r.slice(0, 1000),
            '',
          ]).flat(),
          'Synthesize a clear, actionable summary. What was accomplished? What issues remain? What should happen next?',
        ].join('\n'),
        emotionalState: 'focused',
      },
      { stream: true },
    );

    await speak(stream);
    await withSynthesis.finished;

    // Clear state
    orchestrationState.current = null;

    await dispatch({
      type: 'orchestrationComplete',
      payload: {
        task: plan.task,
        mode: plan.mode,
        phases: plan.steps.map(s => s.phase),
        stepCount: plan.steps.length,
      },
    });

    log('Orchestration complete, returning to initialProcess');
    return [withSynthesis, 'initialProcess'];
  }

  // More steps remain — stay in orchestrator (explicit tuple)
  return [workingMemory, 'orchestrator'];
};

export default orchestrator;
