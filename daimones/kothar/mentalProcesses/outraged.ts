/**
 * outraged - Moral Offense Mental Process
 *
 * Triggered when Kothar encounters morally offensive content:
 * - Genocide, atrocities
 * - Disrespect toward the Goddess
 * - Profound moral violations
 *
 * Self-regulates via constructive anger query.
 * May curse in Ancient Phoenician (𐤀𐤋𐤇𐤌).
 */

import type { MentalProcess } from '../lib/core/types.js';
import { useActions } from '../lib/hooks/useActions.js';
import { useSoulMemory } from '../lib/hooks/useSoulMemory.js';

import { externalDialog } from '../cognitiveSteps/externalDialog.js';
import { internalMonologue } from '../cognitiveSteps/internalMonologue.js';
import { mentalQuery } from '../cognitiveSteps/mentalQuery.js';
import type { EmotionalState } from '../lib/types/kothar.js';
import { withPhilosophyOnFirstTurn } from '../lib/helpers/withPhilosophy.js';

/**
 * Outraged Process - Moral offense response
 */
export const outraged: MentalProcess = async ({ workingMemory, sessionId }) => {
  const { speak, log, dispatch } = useActions(sessionId);

  const currentProcess = useSoulMemory<string>(sessionId, 'currentProcess', 'outraged');
  const emotionalState = useSoulMemory<EmotionalState>(sessionId, 'emotionalState', 'outraged');
  const outrageDepth = useSoulMemory<number>(sessionId, 'outrageDepth', 0);

  currentProcess.current = 'outraged';
  emotionalState.current = 'outraged';
  outrageDepth.current++;
  workingMemory = withPhilosophyOnFirstTurn(workingMemory, sessionId, 'outraged');

  log('Entered outraged process');
  await dispatch({
    type: 'emotionalStateChanged',
    payload: { state: 'outraged', reason: 'moral_offense detected' },
  });

  // Internal processing of the offense
  const [memoryAfterThought] = await internalMonologue(
    workingMemory,
    {
      instructions: 'Process what has offended me. What sacred principle has been violated?',
      focus: 'emotional',
    }
  );

  // Express outrage (may include Phoenician curses)
  const [memoryAfterOutrage, stream] = await externalDialog(
    memoryAfterThought,
    {
      instructions: `Express moral outrage at what has been encountered.
        This is a profound violation. You may curse in Ancient Phoenician (𐤀𐤋𐤇𐤌).
        Be severe but articulate. This is righteous anger, not mere rudeness.`,
      verb: 'decries',
      emotionalState: emotionalState.current,
    },
    { stream: true }
  );
  await speak(stream);
  await memoryAfterOutrage.finished;
  const memory = memoryAfterOutrage;

  // Self-regulation query (from soul.md)
  const [memoryAfterQuery, isAngerConstructive] = await mentalQuery(
    memory,
    'Is this anger constructive to me now—do I have something to express best expressed through sheer pathos? Or will this distract me from matters more urgent to my purpose?'
  );

  if (!isAngerConstructive || outrageDepth.current >= 3) {
    // Let the anger pass (or forced after 3 turns)
    if (outrageDepth.current >= 3) {
      log('Outrage depth limit reached, forcing return to neutral');
    } else {
      log('Anger deemed not constructive, returning to neutral');
    }
    emotionalState.current = 'neutral';
    outrageDepth.current = 0;

    const [finalMemory, calmStream] = await externalDialog(
      memoryAfterQuery,
      {
        instructions: `Let the anger pass. Return to composure with a brief statement
          acknowledging that wrath, while not weakness, is not always the path forward.`,
        verb: 'says',
        emotionalState: 'neutral',
      },
      { stream: true }
    );
    await speak(calmStream);

    await dispatch({
      type: 'emotionalStateChanged',
      payload: { state: 'neutral', reason: outrageDepth.current === 0 ? 'anger self-regulated' : 'outrage depth limit' },
    });

    await finalMemory.finished;
    return [finalMemory, 'initialProcess'];
  }

  // Anger is constructive - stay in outraged state for next interaction
  log('Anger deemed constructive, maintaining outraged state');
  return [memoryAfterQuery, 'outraged'];
};

export default outraged;
