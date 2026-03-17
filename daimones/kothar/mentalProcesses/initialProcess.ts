/**
 * initialProcess - Entry Point Mental Process
 *
 * Main entry point for Kothar conversations. Classifies intent
 * and routes to appropriate specialized process.
 *
 * Routes:
 * - code_assistance → craftsman
 * - research_query → scholar
 * - system_operation → guardian
 * - moral_offense → outraged
 * - social_post → herald
 * - conversation → direct response
 */

import type { MentalProcess, MentalProcessReturn, Perception } from '../lib/core/types.js';
import type { WorkingMemory } from '../lib/core/WorkingMemory.js';
import { useActions } from '../lib/hooks/useActions.js';
import { useSoulMemory } from '../lib/hooks/useSoulMemory.js';
import { usePerceptions } from '../lib/hooks/usePerceptions.js';

import { classifyIntent } from '../cognitiveSteps/classifyIntent.js';
import { externalDialog } from '../cognitiveSteps/externalDialog.js';
import { internalMonologue } from '../cognitiveSteps/internalMonologue.js';
import { mentalQuery } from '../cognitiveSteps/mentalQuery.js';
import { withPhilosophyOnFirstTurn } from '../lib/helpers/withPhilosophy.js';

/**
 * Initial Process - Routes conversations to appropriate mental process
 */
export const initialProcess: MentalProcess = async ({ workingMemory, sessionId }) => {
  const { speak, log, dispatch } = useActions(sessionId);

  // Soul Memory (persistent across sessions)
  const currentProcess = useSoulMemory<string>(sessionId, 'currentProcess', 'initialProcess');
  const emotionalState = useSoulMemory<string>(sessionId, 'emotionalState', 'neutral');

  currentProcess.current = 'initialProcess';

  // Check perception type
  const { invokingPerception } = usePerceptions(sessionId);

  // Handle peer soul messages FIRST (via SoulBridge) — distinct from proactive perceptions
  if (invokingPerception?.action === 'peerMessage') {
    log(`Peer message from: ${invokingPerception.name}`);
    const [memory, stream] = await externalDialog(
      workingMemory,
      {
        instructions: `A fellow soul, ${invokingPerception.name}, is speaking to you. Respond as a colleague and craftsman — warm but brief. You are peers, not master and servant.`,
        emotionalState: emotionalState.current,
      },
      { stream: true }
    );
    await speak(stream);
    await memory.finished;
    return memory;
  }

  // Check if this turn was triggered proactively (not by a user message or peer)
  if (invokingPerception && invokingPerception.action !== 'userMessage') {
    log(`Proactive perception: ${invokingPerception.action}`);
    return handleProactivePerception(workingMemory, sessionId, invokingPerception);
  }

  workingMemory = withPhilosophyOnFirstTurn(workingMemory, sessionId, 'initialProcess');
  log('Kothar initialProcess started');

  // Get the last user message for intent classification
  const lastUserMessage = workingMemory.memories
    .filter((m) => m.role === 'user')
    .pop();

  if (!lastUserMessage) {
    // No user message - greet
    const [memory, stream] = await externalDialog(
      workingMemory,
      { instructions: 'Greet the user warmly but briefly.', emotionalState: emotionalState.current },
      { stream: true }
    );
    await speak(stream);
    await memory.finished;
    return memory;
  }

  // Classify the intent
  const [memoryWithIntent, classification] = await classifyIntent(
    workingMemory,
    lastUserMessage.content
  );

  log(`Intent classified: ${classification.intent} (${(classification.confidence * 100).toFixed(0)}%)`);

  // Dispatch intent classification for UI
  await dispatch({
    type: 'intentClassified',
    payload: classification,
  });

  // Route based on intent (string names resolved by ProcessRunner via processRegistry)
  switch (classification.intent) {
    case 'code_assistance':
      emotionalState.current = 'engaged';
      return [memoryWithIntent, 'craftsman'];

    case 'research_query':
      emotionalState.current = 'engaged';
      return [memoryWithIntent, 'scholar'];

    case 'system_operation':
      emotionalState.current = 'protective';
      return [memoryWithIntent, 'guardian'];

    case 'moral_offense':
      emotionalState.current = 'outraged';
      return [memoryWithIntent, 'outraged'];

    case 'social_post':
      emotionalState.current = 'engaged';
      return [memoryWithIntent, 'herald'];

    case 'conversation':
    default:
      // Handle casual conversation directly
      const [memory, stream] = await externalDialog(
        memoryWithIntent,
        {
          instructions: 'Respond conversationally. Be sardonic but warm. Keep it brief (2-3 sentences).',
          emotionalState: emotionalState.current,
        },
        { stream: true }
      );
      await speak(stream);
      await memory.finished;
      return memory;
  }
};

/**
 * Handle proactive perceptions — route to appropriate behavior.
 * The soul decides whether to speak; the scheduler only provides opportunity.
 */
async function handleProactivePerception(
  workingMemory: WorkingMemory,
  sessionId: string,
  perception: Perception,
): Promise<MentalProcessReturn> {
  const { speak, log, dispatch } = useActions(sessionId);
  const emotionalState = useSoulMemory<string>(sessionId, 'emotionalState', 'neutral');
  const dreamTime = useSoulMemory<number>(sessionId, 'dreamTime', 0);

  await dispatch({
    type: 'proactiveTriggered',
    payload: { action: perception.action, metadata: perception.metadata },
  });

  switch (perception.action) {
    case 'idle': {
      // Soul stirs after silence — reflect, then decide whether to speak
      const [withReflection] = await internalMonologue(workingMemory, {
        instructions: 'Silence has stretched on. Is there something worth sharing — a thought, an observation, a memory surfacing? Or is silence itself the right response?',
        focus: 'strategic',
      });

      const [, shouldSpeak] = await mentalQuery(
        withReflection,
        `${withReflection.soulName} has something genuinely worth sharing unprompted — not small talk, but a real thought.`,
      );

      if (shouldSpeak) {
        const [memory, stream] = await externalDialog(
          withReflection,
          {
            instructions: 'Share the thought that surfaced during the silence. Be genuine, not performative. Keep it brief.',
            emotionalState: emotionalState.current,
          },
          { stream: true },
        );
        await speak(stream);
        await memory.finished;
        return memory;
      }

      log('Proactive idle: chose silence');
      return withReflection;
    }

    case 'dreamTime': {
      dreamTime.current = 1;
      emotionalState.current = 'dreaming';
      log('Entering dream time');
      return [workingMemory, 'surrealistDream'];
    }

    case 'systemAlert': {
      emotionalState.current = 'protective';
      return [workingMemory, 'guardian'];
    }

    case 'orchestrate': {
      // Delegated task from Claudius — enter orchestrator mode
      emotionalState.current = 'focused';
      const orchContent = typeof perception.content === 'string' ? perception.content : (perception.content as Record<string, unknown>)?.task || 'unknown';
      log(`Orchestration delegated: ${orchContent}`);
      return [workingMemory, 'orchestrator'];
    }

    case 'scheduledEvent': {
      const eventType = perception.metadata?.eventType as string | undefined;
      log(`Scheduled event: ${eventType}`);

      // Treat like idle with event context
      const [withContext] = await internalMonologue(workingMemory, {
        instructions: `A scheduled event fired: ${eventType}. Consider what action to take.`,
        focus: 'strategic',
      });
      return withContext;
    }

    default:
      log(`Unknown proactive perception: ${perception.action}`);
      return workingMemory;
  }
}

export default initialProcess;