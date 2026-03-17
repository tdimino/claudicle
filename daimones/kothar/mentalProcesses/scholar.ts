/**
 * scholar - Research Mental Process
 *
 * Kothar as scholar, Opus as field researcher. Two-tier model:
 *
 * 1. Questions answerable from RAG + Kothar's own knowledge → Kothar responds directly
 * 2. Questions needing external sources (web search, papers, docs) → Kothar frames
 *    the research question, spawns an Opus 4.6 session to gather sources, then
 *    synthesizes findings with his own scholarly voice
 *
 * Primary domains: Minoan civilization, Ancient Near East, Goddess traditions,
 * etymology and linguistics. Deeper RAG engagement for primary domain queries.
 *
 * Cost model: RAG retrieval + Kothar reasoning is cheap (local/Groq).
 * Only external research burns Opus tokens.
 */

import type { MentalProcess } from '../lib/core/types.js';
import { useActions } from '../lib/hooks/useActions.js';
import { useSoulMemory } from '../lib/hooks/useSoulMemory.js';

import { scholarlyReflection } from '../cognitiveSteps/scholarlyReflection.js';
import { internalMonologue } from '../cognitiveSteps/internalMonologue.js';
import { externalDialog } from '../cognitiveSteps/externalDialog.js';
import { mentalQuery } from '../cognitiveSteps/mentalQuery.js';
import { getContainer } from '../lib/container.js';
import { searchRAG, formatRAGResults } from '../lib/ragHelpers.js';
import { withPhilosophyOnFirstTurn } from '../lib/helpers/withPhilosophy.js';

// Orchestrator API endpoint (registered via portless)
const ORCHESTRATOR_URL = 'http://claudicle-api.localhost:1355';
const ORCHESTRATOR_TOKEN = process.env.CLAUDICLE_API_TOKEN || '';

/**
 * Spawn an Opus 4.6 Claude Code session for external research.
 */
async function spawnResearchSession(prompt: string): Promise<string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (ORCHESTRATOR_TOKEN) headers['Authorization'] = `Bearer ${ORCHESTRATOR_TOKEN}`;

  const response = await fetch(`${ORCHESTRATOR_URL}/api/orchestrate`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ task: prompt }),
  });

  if (!response.ok) {
    const err = await response.text();
    throw new Error(`Orchestrator API error (${response.status}): ${err}`);
  }

  const data = await response.json() as { result: string; thread_id: string };
  return data.result;
}

/**
 * Scholar Process - Kothar reasons, Opus researches when needed
 */
export const scholar: MentalProcess = async ({ workingMemory, sessionId }) => {
  const { speak, log, dispatch } = useActions(sessionId);

  const currentProcess = useSoulMemory<string>(sessionId, 'currentProcess', 'scholar');
  const emotionalState = useSoulMemory<string>(sessionId, 'emotionalState', 'engaged');
  currentProcess.current = 'scholar';
  workingMemory = withPhilosophyOnFirstTurn(workingMemory, sessionId, 'scholar');

  log('Entered scholar process');
  await dispatch({
    type: 'processTransition',
    payload: { process: 'scholar', reason: 'research_query intent' },
  });

  const lastUserMessage = workingMemory.memories
    .filter((m) => m.role === 'user')
    .pop();

  if (!lastUserMessage) {
    return [workingMemory, 'initialProcess'];
  }

  // Check if this is in Kothar's primary domain
  const [memAfterDomain, isPrimaryDomain] = await mentalQuery(
    workingMemory,
    'This query relates to Minoan civilization, the Ancient Near East, the Goddess traditions, etymology, or Semitic linguistics.',
  );

  // Retrieve RAG context
  let memWithRAG = memAfterDomain;
  let ragFound = false;
  try {
    const container = getContainer();
    const collections = isPrimaryDomain
      ? ['academic-research', 'kothar-conceptual']
      : ['kothar-conceptual'];
    const ragResults = await searchRAG(container.rag, lastUserMessage.content, collections);
    if (ragResults.length > 0) {
      memWithRAG = memWithRAG.withRegion('rag-context', formatRAGResults(ragResults));
      ragFound = true;
      log(`RAG: ${ragResults.length} results from ${collections.join(', ')}`);
    }
  } catch {
    // RAG not available
  }

  // Think about the question
  const [memAfterThought] = await internalMonologue(
    memWithRAG,
    {
      instructions: [
        'Consider this research question carefully.',
        'What do I know from my own scholarly memory and the RAG sources?',
        'Is this something I can answer thoroughly from what I have,',
        'or does it require external research -- web searches, paper lookups,',
        'documentation fetches -- that I cannot do myself?',
      ].join('\n'),
      focus: 'memory',
    },
  );

  // Gate: can Kothar answer from existing knowledge, or does this need external research?
  const [memAfterGate, needsExternalResearch] = await mentalQuery(
    memAfterThought,
    'This question requires information I do not have -- recent publications, specific web content, documentation for a library or tool, or facts I am uncertain about. My RAG sources and training knowledge are insufficient for a thorough answer.',
  );

  if (!needsExternalResearch) {
    // ── Direct answer: Kothar has enough knowledge ──────────────────
    log('Answering from existing knowledge + RAG');

    const depth = isPrimaryDomain ? 'comprehensive' : 'moderate';
    const [memory, stream] = await scholarlyReflection(
      memAfterGate,
      { query: lastUserMessage.content, depth },
      { stream: true },
    );
    await speak(stream);
    await memory.finished;
    return [memory, 'initialProcess'];
  }

  // ── External research: Kothar frames, Opus gathers ──────────────

  log('External research needed -- framing for Opus');

  // Kothar formulates the research brief
  const [memWithBrief] = await internalMonologue(
    memAfterGate,
    {
      instructions: [
        'I need to delegate external research to Claude Code (Opus 4.6).',
        'Frame a precise research brief:',
        '1. What specific questions need answering',
        '2. What sources to look for (papers, docs, web pages, repos)',
        '3. What I already know (so Opus does not duplicate)',
        '4. What format I want the findings in (structured, with citations)',
        '',
        'Be specific about what I need. Opus has web search, firecrawl,',
        'exa-search, academic-research skill -- all the tools I lack.',
      ].join('\n'),
      focus: 'strategic',
    },
  );

  // Extract the research brief
  const [, researchBrief] = await externalDialog(
    memWithBrief,
    {
      instructions: [
        'Write a research brief for Claude Code.',
        'This will be sent as a prompt to an Opus 4.6 session with full tool access.',
        'Be specific about what to search for, what sources to consult, and what to return.',
        'Ask for structured findings with citations and source URLs.',
        'Do NOT include meta-commentary -- just the research task.',
      ].join('\n'),
      verb: 'delegates',
      emotionalState: 'focused',
    },
  );

  // Announce the delegation
  const [memAnnounced, announceStream] = await externalDialog(
    memWithBrief,
    {
      instructions: [
        'Briefly tell the user you are sending a field researcher to gather sources.',
        'One sentence. Convey that you will synthesize the findings yourself.',
      ].join('\n'),
      verb: 'announces',
      emotionalState: 'engaged',
    },
    { stream: true },
  );
  await speak(announceStream);
  await memAnnounced.finished;

  await dispatch({
    type: 'scholarDelegation',
    payload: { brief: typeof researchBrief === 'string' ? researchBrief.slice(0, 200) : '' },
  });

  // Spawn Opus session for research
  log('Spawning Opus 4.6 research session');
  let researchResult: string;

  try {
    const prompt = typeof researchBrief === 'string' ? researchBrief : String(researchBrief);
    researchResult = await spawnResearchSession(prompt);
    log(`Research session complete: ${researchResult.length} chars`);
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    log(`Research session failed: ${errorMsg}`);

    // Fall back to answering from what we have
    const [memFallback, fallbackStream] = await scholarlyReflection(
      memAnnounced,
      {
        query: lastUserMessage.content,
        depth: 'moderate',
      },
      { stream: true },
    );
    await speak(fallbackStream);
    await memFallback.finished;
    return [memFallback, 'initialProcess'];
  }

  // ── Synthesis: Kothar integrates findings with his own voice ─────

  log('Synthesizing research findings');

  const memWithFindings = memAnnounced.withRegion(
    'research-findings',
    `External research (via Opus 4.6):\n${researchResult.slice(0, 4000)}`,
  );

  // Kothar synthesizes with scholarly authority
  const [memSynthesized, synthesisStream] = await scholarlyReflection(
    memWithFindings,
    {
      query: lastUserMessage.content,
      depth: isPrimaryDomain ? 'comprehensive' : 'moderate',
    },
    { stream: true },
  );
  await speak(synthesisStream);
  await memSynthesized.finished;

  await dispatch({
    type: 'scholarComplete',
    payload: { delegated: true, resultLength: researchResult.length },
  });

  return [memSynthesized, 'initialProcess'];
};

export default scholar;
