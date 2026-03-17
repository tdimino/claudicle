/**
 * herald - Twitter Posting Mental Process
 *
 * Composes and posts tweets with Kothar's voice, grounded in RAG knowledge,
 * accompanied by a generated image of Kothar's avatar in a relevant locale.
 *
 * Two-turn draft+approve flow:
 *   Turn 1 (no pending draft):
 *     1. internalMonologue: Determine topic and angle
 *     2. RAG query: Ground in academic knowledge
 *     3. composeTweet: Craft ≤280-char tweet
 *     4. GeminiImageGenerator: Kothar's avatar in locale
 *     5. SmolVLM: Describe the image
 *     6. externalDialog: Present draft to user
 *     7. Stay in herald for approval
 *
 *   Turn 2 (pending draft exists):
 *     1. mentalQuery: Did the user approve?
 *     2a. Approved → post via bird CLI + log to memory
 *     2b. Edit → re-compose + present again
 *     2c. Rejected → withdraw + return to initialProcess
 */

import type { MentalProcess } from '../lib/core/types.js';
import { useActions } from '../lib/hooks/useActions.js';
import { useSoulMemory } from '../lib/hooks/useSoulMemory.js';
import { getContainer } from '../lib/container.js';

import { internalMonologue } from '../cognitiveSteps/internalMonologue.js';
import { externalDialog } from '../cognitiveSteps/externalDialog.js';
import { composeTweet } from '../cognitiveSteps/composeTweet.js';
import { mentalQuery } from '../cognitiveSteps/mentalQuery.js';
import { searchRAG, formatRAGResults } from '../lib/ragHelpers.js';
import { MemoryWriter } from '../lib/MemoryWriter.js';

const memoryWriter = new MemoryWriter('./memory');

/**
 * herald - Twitter posting process
 */
export const herald: MentalProcess = async ({ workingMemory, sessionId }) => {
  const { speak, log, dispatch } = useActions(sessionId);

  const currentProcess = useSoulMemory<string>(sessionId, 'currentProcess', 'herald');
  const emotionalState = useSoulMemory<string>(sessionId, 'emotionalState', 'neutral');
  const lastTweetText = useSoulMemory<string>(sessionId, 'lastTweetText', '');
  const lastTweetImage = useSoulMemory<string>(sessionId, 'lastTweetImage', '');
  const lastTweetImageDesc = useSoulMemory<string>(sessionId, 'lastTweetImageDesc', '');

  currentProcess.current = 'herald';

  log('Entered herald process');
  await dispatch({
    type: 'processTransition',
    payload: { process: 'herald', reason: 'social_post intent' },
  });

  let step = workingMemory;

  // ─── Turn 2: Approval (if a draft is pending) ───

  if (lastTweetText.current) {
    log('Herald: pending draft detected, processing approval');
    return handleApproval(step, sessionId);
  }

  // ─── Turn 1: Draft ───

  // Step 1: Determine topic and angle
  const [withTopic, topicThought] = await internalMonologue(step, {
    instructions: 'What is worth sharing publicly on Twitter? What angle would resonate — scholarly, mythological, craftsman insight? Consider what would intrigue mortals scrolling their feeds. The 280-character constraint demands precision.',
    focus: 'strategic',
  });

  step = withTopic;
  log('Herald: topic determined:', topicThought);

  // Step 2: RAG grounding (if scholarly topic)
  let ragSummary = '';
  try {
    const container = getContainer();
    const ragResults = await searchRAG(
      container.rag,
      topicThought,
      ['academic-research', 'kothar-conceptual'],
      3,
    );
    if (ragResults.length > 0) {
      ragSummary = formatRAGResults(ragResults);
      step = step.withRegion('rag-context', ragSummary);
      log(`Herald: RAG returned ${ragResults.length} results`);
    }
  } catch (error) {
    log('Herald: RAG retrieval failed, continuing without context', error);
  }

  // Step 3: Compose tweet text
  const [withDraft, draftText] = await composeTweet(step, {
    topic: topicThought,
    ragContext: ragSummary || undefined,
  });

  step = withDraft;
  log(`Herald: tweet composed (${draftText.length} chars):`, draftText);

  // Step 4: Generate avatar image
  let tweetImagePath: string | null = null;
  let tweetImageDesc: string | null = null;

  const container = getContainer();
  if (container.imageGenerator && container.config.features?.twitter) {
    try {
      log('Herald: generating avatar image...');
      const imagePrompt = buildTweetImagePrompt(step.soulName, topicThought, draftText);
      const imageResult = await container.imageGenerator.generate(imagePrompt, {
        canvasSubdir: 'tweets',
        temperature: 0.8,
        aspectRatio: '16:9',
      });
      tweetImagePath = imageResult.imagePath;
      log('Herald: image generated:', tweetImagePath);

      // Step 5: SmolVLM describes the image
      if (container.vision && tweetImagePath) {
        const visionResult = await container.vision.describe(
          tweetImagePath,
          `Describe this image of ${step.soulName}, the divine craftsman, in the scene depicted.`,
        );
        tweetImageDesc = visionResult.description;
        log('Herald: image described:', tweetImageDesc);
      }
    } catch (err) {
      log('Herald: image generation failed (non-fatal):', String(err));
    }
  }

  // Step 6: Present draft via externalDialog
  const imageNote = tweetImagePath
    ? `\n\nI have summoned a vision: ${tweetImagePath}${tweetImageDesc ? `\n${tweetImageDesc}` : ''}`
    : '';

  const [withPresentation, presentationStream] = await externalDialog(
    step,
    {
      instructions: `${step.soulName} is presenting a draft tweet for approval. Show the tweet text and describe the accompanying image if present. Ask the user to approve, edit, or withdraw. Be brief — the tweet itself is the focus.\n\nDraft tweet: "${draftText}"${imageNote}`,
      verb: 'presents',
      emotionalState: emotionalState.current,
    },
    { stream: true },
  );
  await speak(presentationStream);

  step = withPresentation;
  await step.finished;

  // Store draft in soul memory for the approval turn
  lastTweetText.current = draftText;
  lastTweetImage.current = tweetImagePath || '';
  lastTweetImageDesc.current = tweetImageDesc || '';

  await dispatch({
    type: 'tweetDrafted',
    payload: {
      text: draftText,
      charCount: draftText.length,
      imagePath: tweetImagePath,
      imageDescription: tweetImageDesc,
    },
  });

  // Stay in herald for the approval turn
  return [step, 'herald'];
};

/**
 * Handle the approval turn — approve, edit, or reject
 */
async function handleApproval(
  workingMemory: import('../lib/core/WorkingMemory.js').WorkingMemory,
  sessionId: string,
): Promise<import('../lib/core/types.js').MentalProcessReturn> {
  const { speak, log, dispatch } = useActions(sessionId);
  const lastTweetText = useSoulMemory<string>(sessionId, 'lastTweetText', '');
  const lastTweetImage = useSoulMemory<string>(sessionId, 'lastTweetImage', '');
  const lastTweetImageDesc = useSoulMemory<string>(sessionId, 'lastTweetImageDesc', '');
  const emotionalState = useSoulMemory<string>(sessionId, 'emotionalState', 'neutral');

  let step = workingMemory;

  // Check if user is making a new tweet request (not responding to the current draft)
  const [, newRequest] = await mentalQuery(
    step,
    'The user is asking to create or post a new tweet about a different topic, not responding to the current draft.',
  );

  if (newRequest) {
    log('Herald: new tweet request detected during approval — clearing draft and restarting');
    clearDraftState(sessionId);
    return [step, 'herald'];
  }

  // Check if user approved
  const [stepAfterQuery, approved] = await mentalQuery(
    step,
    'The user has approved the tweet for posting (said yes, post it, go ahead, looks good, or similar affirmation).',
  );

  if (approved) {
    // Post via bird CLI
    const container = getContainer();
    const tweetText = lastTweetText.current;
    const imagePath = lastTweetImage.current;
    const imageDesc = lastTweetImageDesc.current;

    log('Herald: posting tweet...');

    try {
      const tweetArgs: Record<string, unknown> = {
        action: 'tweet',
        text: tweetText,
      };
      if (imagePath) {
        tweetArgs.media = imagePath;
        if (imageDesc) {
          tweetArgs.alt = imageDesc.slice(0, 1000); // Alt text limit
        }
      }

      const result = await container.skills.invoke('twitter', tweetArgs);

      if (result.success) {
        log('Herald: tweet posted successfully');

        // Log to memory
        try {
          const date = new Date().toISOString().split('T')[0];
          await memoryWriter.writeMemory({
            type: 'episodic',
            title: `Tweet: ${tweetText.slice(0, 50)}`,
            content: `## Tweet\n\n${tweetText}\n\n${imagePath ? `![Tweet image](${imagePath})\n` : ''}${imageDesc ? `*${imageDesc}*\n` : ''}`,
            tags: ['tweet', 'herald', 'social'],
            participants: ['Kothar'],
            date,
          });
        } catch (err) {
          log('Herald: failed to log tweet to memory:', String(err));
        }

        // Confirmation
        const [withConfirmation, confirmStream] = await externalDialog(
          stepAfterQuery,
          {
            instructions: `${stepAfterQuery.soulName} has successfully posted the tweet. Confirm briefly — something like the inscription has been dispatched to the agora. One sentence.`,
            verb: 'announces',
            emotionalState: emotionalState.current,
          },
          { stream: true },
        );
        await speak(confirmStream);
        step = withConfirmation;
        await step.finished;

        await dispatch({
          type: 'tweetPosted',
          payload: { text: tweetText, imagePath, output: result.output },
        });
      } else {
        log('Herald: tweet posting failed:', result.error);
        const [withError, errorStream] = await externalDialog(
          stepAfterQuery,
          {
            instructions: `The tweet failed to post. Error: ${result.error}. Express frustration briefly.`,
            verb: 'mutters',
            emotionalState: 'frustrated',
          },
          { stream: true },
        );
        await speak(errorStream);
        step = withError;
        await step.finished;
      }
    } catch (err) {
      log('Herald: tweet posting threw:', String(err));
      const [withError, errorStream] = await externalDialog(
        stepAfterQuery,
        {
          instructions: `The tweet failed to post due to a technical error. Express brief frustration.`,
          verb: 'mutters',
          emotionalState: 'frustrated',
        },
        { stream: true },
      );
      await speak(errorStream);
      step = withError;
      await step.finished;
    }

    // Clear draft state
    clearDraftState(sessionId);
    return [step, 'initialProcess'];
  }

  // Check if user wants to edit
  const [, wantsEdit] = await mentalQuery(
    stepAfterQuery,
    'The user wants to modify, adjust, or edit the tweet (not a full rejection).',
  );

  if (wantsEdit) {
    log('Herald: user wants edits — re-composing');

    // Get the user's last message for edit instructions
    const lastUserMsg = stepAfterQuery.memories
      .filter((m) => m.role === 'user')
      .pop();
    const editInstructions = lastUserMsg?.content || 'Make adjustments';

    // Re-compose with edit context
    const [withRedraft, newDraft] = await composeTweet(stepAfterQuery, {
      topic: `Revise the previous tweet: "${lastTweetText.current}"\n\nUser's edit request: ${editInstructions}`,
    });

    step = withRedraft;
    lastTweetText.current = newDraft;

    // Present revised draft
    const [withPresentation, stream] = await externalDialog(
      step,
      {
        instructions: `${step.soulName} has revised the tweet. Present the new draft: "${newDraft}" (${newDraft.length} chars). Ask for approval.`,
        verb: 'presents',
        emotionalState: emotionalState.current,
      },
      { stream: true },
    );
    await speak(stream);
    step = withPresentation;
    await step.finished;

    // Stay in herald for another approval round
    return [step, 'herald'];
  }

  // User rejected
  log('Herald: user rejected the tweet');
  const [withRejection, rejectionStream] = await externalDialog(
    stepAfterQuery,
    {
      instructions: `${stepAfterQuery.soulName} withdraws the tweet draft. Brief, dignified — one sentence.`,
      verb: 'concedes',
      emotionalState: emotionalState.current,
    },
    { stream: true },
  );
  await speak(rejectionStream);
  step = withRejection;
  await step.finished;

  clearDraftState(sessionId);
  return [step, 'initialProcess'];
}

/**
 * Clear all draft state from soul memory
 */
function clearDraftState(sessionId: string): void {
  const lastTweetText = useSoulMemory<string>(sessionId, 'lastTweetText', '');
  const lastTweetImage = useSoulMemory<string>(sessionId, 'lastTweetImage', '');
  const lastTweetImageDesc = useSoulMemory<string>(sessionId, 'lastTweetImageDesc', '');
  lastTweetText.current = '';
  lastTweetImage.current = '';
  lastTweetImageDesc.current = '';
}

/**
 * Build image prompt placing Kothar's avatar in a locale
 */
function buildTweetImagePrompt(
  soulName: string,
  topic: string,
  tweetText: string,
): string {
  return `A portrait of ${soulName}, a bronze-skinned divine craftsman of ancient Thera,
in a scene related to: ${topic}

The scene should place ${soulName} in a specific, evocative locale that connects to the topic.
If the topic is about frescoes, he stands before painted walls.
If about metalwork, he is at a forge with molten bronze.
If about the sea, he watches from the caldera's edge.
If about scholarship, he sits in a stone library with clay tablets.

Tweet being composed: "${tweetText.slice(0, 200)}"

Style: Photorealistic with mythological grandeur. Bronze Age Mediterranean.
Warm earth tones, Aegean blue accents, volcanic amber light.
${soulName} should be recognizable as a consistent character — muscular build,
dark curly hair, knowing eyes, wearing a craftsman's leather apron.
16:9 cinematic composition.`;
}

export default herald;
