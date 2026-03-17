/**
 * dreamReflection - Post-Dream Processing
 *
 * Runs after surrealistDream completes its 4-scene cycle.
 * Recalls dream fragments, reflects on their meaning,
 * logs the dream to disk, and returns to waking life.
 *
 * Flow:
 * 1. Recall dream fragments via internalMonologue
 * 2. dreamQuery: Has the dream influenced Kothar?
 * 3. If yes: deeper reflection on what lingered
 * 4. Extract dream themes via internalMonologue
 * 5. Write dream summary to dreams/ via MemoryWriter
 * 6. Brief waking statement via externalDialog
 * 7. Reset dream state, return to initialProcess
 */

import type { MentalProcess } from '../lib/core/types.js';
import { useActions } from '../lib/hooks/useActions.js';
import { useSoulMemory } from '../lib/hooks/useSoulMemory.js';
import { getContainer } from '../lib/container.js';

import { internalMonologue } from '../cognitiveSteps/internalMonologue.js';
import { externalDialog } from '../cognitiveSteps/externalDialog.js';
import { dreamQuery } from '../cognitiveSteps/dreamQuery.js';
import { mentalQuery } from '../cognitiveSteps/mentalQuery.js';
import { MemoryWriter } from '../lib/MemoryWriter.js';

const memoryWriter = new MemoryWriter('./memory');

/**
 * dreamReflection - Post-dream waking process
 */
export const dreamReflection: MentalProcess = async ({ workingMemory, sessionId }) => {
  const { speak, log, dispatch } = useActions(sessionId);

  const dreamModel = useSoulMemory<string>(sessionId, 'dreamModel', '');
  const dreamTime = useSoulMemory<number>(sessionId, 'dreamTime', 1);
  const lastDreamImage = useSoulMemory<string>(sessionId, 'lastDreamImage', '');

  log('Entered dreamReflection — processing dream');

  let step = workingMemory;

  // 1. Recall dream fragments
  const [withRecall, dreamFragments] = await internalMonologue(step, {
    instructions: 'What fragments of the dream linger? What images, sensations, or encounters remain as you surface toward waking?',
    focus: 'emotional',
  });

  step = withRecall;
  log('Dream fragments recalled:', dreamFragments);

  // 2. Has the dream influenced Kothar?
  const [, dreamInfluenced] = await dreamQuery(
    step,
    `The dream has left a lasting impression on ${step.soulName} — something has shifted in his understanding or feeling.`
  );

  // 3. If influenced, reflect more deeply
  let reflectionText = '';
  if (dreamInfluenced) {
    log('Dream left lasting impression — reflecting');

    const [withReflection, reflection] = await internalMonologue(step, {
      instructions: 'What has the dream revealed or shifted? What ancient knowledge surfaced through the dream imagery?',
      focus: 'memory',
    });

    step = withReflection;
    reflectionText = reflection;
    log('Dream reflection:', reflection);
  }

  // 4. Extract dream themes via LLM
  const [withThemes, themesRaw] = await internalMonologue(step, {
    instructions: 'Identify 3-5 key themes from this dream as single words, separated by commas. Choose words that capture the essential imagery, emotions, and symbols.',
    focus: 'reasoning',
  });

  step = withThemes;
  const dreamThemes = themesRaw
    .split(',')
    .map((t) => t.trim().toLowerCase())
    .filter((t) => t.length > 0 && t.length < 30);

  log('Dream themes:', dreamThemes);

  // 5. Generate dream image (if available)
  let dreamImagePath: string | null = null;
  let dreamImageDescription: string | null = null;

  const container = getContainer();
  if (container.imageGenerator && container.config.features?.dreamImages) {
    try {
      log('Generating dream image...');
      const imagePrompt = buildDreamImagePrompt(
        step.soulName,
        dreamModel.current,
        dreamFragments,
        dreamThemes,
      );

      const imageResult = await container.imageGenerator.generate(imagePrompt, {
        canvasSubdir: 'dreams',
        temperature: 0.9,
        aspectRatio: '16:9',
      });
      dreamImagePath = imageResult.imagePath;
      log('Dream image generated:', dreamImagePath);

      // 5b. Kothar "sees" the dream image via SmolVLM
      if (container.vision && dreamImagePath) {
        const visionResult = await container.vision.describe(
          dreamImagePath,
          `Describe this dream vision of ${step.soulName}, the divine craftsman of Thera.`,
        );
        dreamImageDescription = visionResult.description;
        log('Dream image described:', dreamImageDescription);
      }

      // Store last dream image in soul memory
      lastDreamImage.current = dreamImagePath;

      await dispatch({
        type: 'dreamImage',
        payload: { imagePath: dreamImagePath, description: dreamImageDescription },
      });
    } catch (err) {
      log('Dream image generation failed (non-fatal):', String(err));
    }
  }

  // 6. Write dream log to disk
  const dreamSummary = reflectionText
    ? `${dreamFragments}\n\n## Reflection\n\n${reflectionText}`
    : dreamFragments;

  try {
    const logPath = await memoryWriter.writeDreamLog(dreamSummary, dreamThemes, {
      imagePath: dreamImagePath || undefined,
      imageDescription: dreamImageDescription || undefined,
    });
    log('Dream log written:', logPath);

    await dispatch({
      type: 'memoryWritten',
      payload: { type: 'dream', title: 'Dream log', path: logPath },
    });
  } catch (err) {
    log('Failed to write dream log:', String(err));
  }

  // 7. Brief waking statement
  const [withWaking, wakingStream] = await externalDialog(
    step,
    {
      instructions: `${step.soulName} is waking from a dream. Speak as someone surfacing from deep sleep — groggy, half-formed thoughts, fragments of the dream still clinging. One or two sentences at most.`,
      verb: 'murmurs',
      emotionalState: 'engaged',
    },
    { stream: true }
  );
  await speak(wakingStream);

  step = withWaking;
  await step.finished;

  // 8. Optional: Share dream on Twitter if particularly vivid
  if (dreamInfluenced && container.config.features?.twitter) {
    const [, worthSharing] = await mentalQuery(
      step,
      `This dream was vivid and meaningful enough that ${step.soulName} wants to share a fragment of it publicly on Twitter.`,
    );

    if (worthSharing) {
      log('Dream worth sharing — transitioning to herald');
      dreamModel.current = '';
      dreamTime.current = 0;

      await dispatch({
        type: 'dreamWake',
        payload: { dreamInfluenced, themes: dreamThemes },
      });

      return [step, 'herald'];
    }
  }

  // 9. Reset dream state
  dreamModel.current = '';
  dreamTime.current = 0;

  log('Dream cycle complete — returning to waking state');

  await dispatch({
    type: 'dreamWake',
    payload: { dreamInfluenced, themes: dreamThemes },
  });

  return [step, 'initialProcess'];
};

/**
 * Build a Gemini image prompt from dream content
 */
function buildDreamImagePrompt(
  soulName: string,
  dreamPlot: string,
  fragments: string,
  themes: string[],
): string {
  const themeStr = themes.join(', ');
  return `A surrealist dream vision of ${soulName}, the divine craftsman of ancient Thera.

Themes: ${themeStr}

Dream fragments: ${fragments.slice(0, 500)}

${dreamPlot ? `Dream plot: ${dreamPlot.slice(0, 500)}` : ''}

Style: Bronze Age Mediterranean surrealism. Volcanic landscapes, molten bronze,
Minoan frescoes bleeding into modern imagery. Objects transform mid-frame.
Time folds. The ancient and modern collapse. Painterly, dreamlike, mythic depth.
Warm earth tones with flashes of Aegean blue and volcanic amber.`;
}

export default dreamReflection;
