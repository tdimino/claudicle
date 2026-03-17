/**
 * Core types for Kothar Soul Engine
 * Adapted from Open Souls functional programming paradigm
 */

// ============================================
// Chat Message Types
// ============================================

export enum ChatMessageRoleEnum {
  System = 'system',
  User = 'user',
  Assistant = 'assistant',
}

export interface Memory {
  role: ChatMessageRoleEnum;
  content: string;
  name?: string;
  metadata?: Record<string, unknown>;
  timestamp?: string;
  region?: string;
}

export interface MemoryRegionConfig {
  ttlMs?: number;
  priority?: number;
}

// ============================================
// Working Memory Types
// ============================================

export interface WorkingMemoryConfig {
  soulName: string;
  memories?: Memory[];
  regionalOrder?: string[];
  systemInstruction?: string;
}

export interface WorkingMemorySnapshot {
  soulName: string;
  memories: Memory[];
  regionalOrder: string[];
  timestamp: string;
}

// ============================================
// Cognitive Step Types
// ============================================

/**
 * Stream processor transforms streamed output in real-time.
 * Used by dialog steps to strip entity/verb prefixes before display.
 */
export type StreamProcessor = (
  workingMemory: WorkingMemory,
  stream: AsyncIterable<string>
) => AsyncIterable<string>;

export interface CognitiveStepConfig<PostProcessReturnType = string> {
  command: (memory: WorkingMemory) => Memory;
  postProcess?: (memory: WorkingMemory, response: string) => Promise<[Memory | null, PostProcessReturnType]>;
  schema?: unknown;
  streamProcessor?: StreamProcessor;
}

export type CognitiveStepFactory<UserArgType, PostProcessReturnType = string> = (
  userArgs: UserArgType
) => CognitiveStepConfig<PostProcessReturnType>;

/**
 * CognitiveStep function signature with streaming overloads
 */
export interface CognitiveStep<UserArgType, PostProcessReturnType = string> {
  (
    memory: WorkingMemory,
    userArgs: UserArgType,
    opts: { stream: true; model?: string; temperature?: number }
  ): Promise<[WorkingMemory, AsyncIterable<string>, Promise<PostProcessReturnType>]>;

  (
    memory: WorkingMemory,
    userArgs: UserArgType,
    opts?: { stream?: false; model?: string; temperature?: number }
  ): Promise<[WorkingMemory, PostProcessReturnType]>;
}

// ============================================
// Mental Process Types
// ============================================

export interface MentalProcessContext<TParams = unknown> {
  workingMemory: WorkingMemory;
  sessionId: string;
  params?: TParams;
}

/**
 * Process identifier — either a direct function reference or a string name
 * resolved at runtime via the soul's processRegistry.
 *
 * Prefer string names to avoid circular imports between mental processes.
 */
export type ProcessIdentifier = MentalProcess | string;

export type MentalProcessReturn<TParams = unknown> =
  | WorkingMemory
  | [WorkingMemory, ProcessIdentifier]
  | [WorkingMemory, ProcessIdentifier, { params?: TParams; executeNow?: boolean }];

export type MentalProcess<TParams = unknown, TransitionParams = unknown> = (
  context: MentalProcessContext<TParams>
) => Promise<MentalProcessReturn<TransitionParams>>;

// ============================================
// LLM Types
// ============================================

export interface LLMMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
  name?: string;
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface GenerateOptions {
  model?: string;
  temperature?: number;
  maxTokens?: number;
  stream?: boolean;
  thinkingEffort?: 'none' | 'low' | 'medium' | 'high';
  onUsage?: (usage: TokenUsage) => void;
}

// ============================================
// Action Types
// ============================================

export interface SoulActions {
  speak: (content: string | AsyncIterable<string>, verb?: string) => Promise<void>;
  log: (message: string, data?: unknown) => void;
  dispatch: (action: DispatchAction) => Promise<void>;
  scheduleEvent: (event: ScheduledEvent) => Promise<string>;
  cancelScheduledEvent: (eventId: string) => boolean;
}

export interface DispatchAction {
  type: string;
  payload: unknown;
}

export interface ScheduledEvent {
  type: string;
  delayMs: number;
  payload?: unknown;
}

// ============================================
// Perception Types
// ============================================

export type PerceptionAction =
  | 'userMessage'
  | 'scheduledEvent'
  | 'idle'
  | 'dreamTime'
  | 'systemAlert'
  | 'peerMessage'
  | 'orchestrate';

export interface Perception {
  action: PerceptionAction;
  content: string | Record<string, unknown>;
  name?: string;
  metadata?: Record<string, unknown>;
}

export interface ProactiveConfig {
  enabled?: boolean;
  /** Min ms between proactive turns (default: 600000 = 10 min) */
  cooldownMs?: number;
  /** Ms of user silence before idle fires (default: 1800000 = 30 min) */
  idleThresholdMs?: number;
  /** Scheduler tick interval in ms (default: 30000 = 30s) */
  tickIntervalMs?: number;
}

// ============================================
// Soul Configuration Types (simplified)
// ============================================

export interface SoulIdentity {
  name: string;
  description?: string;
  personality?: string;
  voice?: string;
}

export interface SoulLLMConfig {
  provider: string;
  model: string;
  fallback?: {
    provider: string;
    model: string;
  };
  temperature?: number;
  maxTokens?: number;
}

export interface SoulPersistenceConfig {
  type: 'json' | 'sqlite' | 'memory';
  path?: string;
}

export interface SoulHardwareConfig {
  monitorInterval?: number;
  thermalThreshold?: number;
}

export interface SoulRAGConfig {
  enabled?: boolean;
  collections?: string[];
}

export interface SoulModelMap {
  default: string;
  persona?: string;
  classifier?: string;
  monologue?: string;
  dialog?: string;
  dream?: string;
  subconscious?: string;
  scholar?: string;
  [key: string]: string | undefined;
}

export interface SoulSamplingMap {
  [role: string]: {
    temperature?: number;
    maxTokens?: number;
  };
}

export interface SoulDaimonChamberConfig {
  port?: number;
  canvasDir?: string;
  autoStart?: boolean;
}

export interface SoulFeaturesConfig {
  systemMonitoring?: boolean;
  skillIntegration?: boolean;
  scholarlyMode?: boolean;
  codeAssistance?: boolean;
  voiceInterface?: boolean;
  dreaming?: boolean;
  daimonicObserver?: boolean;
  webResearch?: boolean;
  daimonChamber?: boolean;
  dreamImages?: boolean;
  twitter?: boolean;
  proactiveMessaging?: boolean;
  [key: string]: boolean | undefined;
}

export interface SoulTriggersConfig {
  idleThreshold?: number;
  systemCheckInterval?: number;
}

export interface SoulDreamingConfig {
  startHour: number;
  endHour: number;
  timezone: string;
}

export interface SoulConfig {
  name: string;
  identity?: SoulIdentity;
  llm: SoulLLMConfig;
  models?: SoulModelMap;
  sampling?: SoulSamplingMap;
  persistence?: SoulPersistenceConfig;
  hardware?: SoulHardwareConfig;
  rag?: SoulRAGConfig;
  features?: SoulFeaturesConfig;
  daimonChamber?: SoulDaimonChamberConfig;
  proactive?: ProactiveConfig;
  triggers?: SoulTriggersConfig;
  dreaming?: SoulDreamingConfig;
}

// Forward declaration for WorkingMemory (implemented in WorkingMemory.ts)
export type WorkingMemory = import('./WorkingMemory').WorkingMemory;
