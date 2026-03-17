/**
 * surrealistDream - Dream State Mental Process
 *
 * Active during sleeping hours (12AM-8AM). Generates 3-4 dream scenes
 * per cycle, narrated by the Kotharot of Crete.
 *
 * Adapted from Samantha-Dreams' surrealistDream.ts:
 * - melatoninCounter tracks scene progression (processMemory)
 * - dreamModel provides the plot (soulMemory, set by dreamGenie)
 * - Scenes bleed into each other with surrealist logic
 * - Tom appears as a dream character inspired by userModel
 * - After 4 scenes: exits → dreamReflection
 */

import type { MentalProcess } from '../lib/core/types.js';
import { ChatMessageRoleEnum } from '../lib/core/types.js';
import { useActions } from '../lib/hooks/useActions.js';
import { useSoulMemory } from '../lib/hooks/useSoulMemory.js';
import { useProcessMemory } from '../lib/hooks/useProcessMemory.js';

import { internalMonologue } from '../cognitiveSteps/internalMonologue.js';
import { dreamQuery } from '../cognitiveSteps/dreamQuery.js';
import { dreamNarration } from '../cognitiveSteps/dreamNarration.js';

/**
 * surrealistDream - 3-4 scene dream progression
 */
export const surrealistDream: MentalProcess = async ({ workingMemory, sessionId }) => {
  const { log, dispatch } = useActions(sessionId);

  const dreamModel = useSoulMemory<string>(sessionId, 'dreamModel', '');
  const dreamTime = useSoulMemory<number>(sessionId, 'dreamTime', 1);
  const userName = useSoulMemory<string>(sessionId, 'userName', 'Tom');
  const userModel = useSoulMemory<string>(sessionId, 'userModel', '');
  const melatoninCounter = useProcessMemory<number>(sessionId, 'surrealistDream', 'melatoninCounter', 0);

  let step = workingMemory;

  // Inject dream context
  step = step.withMemory({
    role: ChatMessageRoleEnum.System,
    content: `${step.soulName} finds himself in this ${dreamModel.current || 'formless void'}, although he is unaware that he is dreaming, or even who he is. Subsequent messages should be interpreted as external stimuli filtering into the dream — distorted, reinterpreted, woven into surreal narrative that flows from one scene to the next based on conceptual associations rather than literal meaning.`,
  });

  // Dream cycle: 4 scenes then wake
  if (melatoninCounter.current < 4) {
    melatoninCounter.current++;
    log(`Dream scene ${melatoninCounter.current}/4`);

    // Scene 1 — Pondering: Where does he wander next?
    const [withPondering, pondering] = await internalMonologue(step, {
      instructions: 'Where should he wander next? What draws him forward through this landscape?',
      focus: 'emotional',
    });

    await dispatch({
      type: 'dreamScene',
      payload: { scene: melatoninCounter.current, phase: 'pondering', content: pondering },
    });

    step = withPondering;
    log('Dream pondering:', pondering);

    // Scene 2 — Narration: The Kotharot sing the scene
    const [withNarration, narrationStream] = await dreamNarration(
      step,
      {
        instructions: 'Narrate a scene continuing from the previous, flowing from one locale to the next. Write 2-4 sentences in 3rd-person omniscient.',
        verb: 'conjures',
      },
      { stream: true }
    );

    await dispatch({
      type: 'dreamScene',
      payload: { scene: melatoninCounter.current, phase: 'narration', content: narrationStream },
    });

    step = withNarration;
    await step.finished;

    // Scene 3 — Voice: Decide who speaks
    const [, kotharSpeaks] = await dreamQuery(
      step,
      `${step.soulName} should speak next in the dream.`
    );

    if (kotharSpeaks) {
      // Kothar speaks as a dream character
      const [withVoice, voiceStream] = await dreamNarration(
        step,
        {
          instructions: `You are a dream character — a figment of ${step.soulName}'s sleeping mind. Speak as ${step.soulName}, half-conscious, voice echoing from far away.`,
          verb: 'voices',
          persona: `${step.soulName}, half-conscious`,
        },
        { stream: true }
      );
      await dispatch({
        type: 'dreamScene',
        payload: { scene: melatoninCounter.current, phase: 'voice', speaker: step.soulName, content: voiceStream },
      });
      step = withVoice;
      await step.finished;
    } else {
      // Tom appears as a dream character
      const [withVoice, voiceStream] = await dreamNarration(
        step,
        {
          instructions: `You are a dream character — a figment of ${step.soulName}'s sleeping mind. Your character and speech are inspired by ${userModel.current || userName.current}.`,
          verb: 'whispers',
          persona: `${userName.current}, as dream figment`,
        },
        { stream: true }
      );
      await dispatch({
        type: 'dreamScene',
        payload: { scene: melatoninCounter.current, phase: 'voice', speaker: userName.current, content: voiceStream },
      });
      step = withVoice;
      await step.finished;
    }

    // Scene 4 — Encounter: The other character responds
    const [, otherSpeaks] = await dreamQuery(
      step,
      `${userName.current} should speak next in the dream.`
    );

    if (otherSpeaks) {
      const [withEncounter, encounterStream] = await dreamNarration(
        step,
        {
          instructions: `You are ${userName.current}, appearing in ${step.soulName}'s dream. Speak as a dream version — half-remembered, transformed by the sleeping mind.`,
          verb: 'riddles',
          persona: `${userName.current}, half-conscious`,
        },
        { stream: true }
      );
      await dispatch({
        type: 'dreamScene',
        payload: { scene: melatoninCounter.current, phase: 'encounter', speaker: userName.current, content: encounterStream },
      });
      step = withEncounter;
      await step.finished;
    } else {
      const [withEncounter, encounterStream] = await dreamNarration(
        step,
        {
          instructions: `${step.soulName} moves through the dream alone. The landscape shifts around him, responding to his passage.`,
          verb: 'muses',
        },
        { stream: true }
      );
      await dispatch({
        type: 'dreamScene',
        payload: { scene: melatoninCounter.current, phase: 'encounter', speaker: step.soulName, content: encounterStream },
      });
      step = withEncounter;
      await step.finished;
    }

    // Stay in dream state for next turn
    return step;
  }

  // Dream cycle complete — wake up
  log('Dream cycle complete, transitioning to dreamReflection');

  await dispatch({
    type: 'dreamWake',
    payload: { scenesCompleted: melatoninCounter.current },
  });

  melatoninCounter.current = 0;
  return [step, 'dreamReflection'];
};

export default surrealistDream;
