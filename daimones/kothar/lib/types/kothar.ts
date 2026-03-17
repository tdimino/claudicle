/**
 * Kothar-specific type definitions
 *
 * Types for intent classification, emotional states, user modeling,
 * and process configuration.
 */

import type { MentalProcess, MentalProcessContext } from '../core/types.js';

/**
 * Intent categories for message classification
 */
export type Intent =
  | 'code_assistance'   // Code architecture, design patterns, debugging
  | 'research_query'    // Academic questions, Minoan/ANE topics, etymology
  | 'system_operation'  // Hardware status, system health queries
  | 'conversation'      // Casual chat, greetings, personal questions
  | 'moral_offense'     // Content involving atrocities, disrespect to the Goddess
  | 'social_post';      // User wants Kothar to compose and post a tweet

/**
 * Emotional state spectrum
 */
export type EmotionalState =
  | 'neutral'      // Default state
  | 'engaged'      // Active, interested in discussion
  | 'protective'   // Defensive about system/hardware
  | 'frustrated'   // Minor friction, may curse in Phoenician
  | 'outraged';    // Moral offense response

/**
 * Intent classification result from classifyIntent cognitive step
 */
export interface IntentClassification {
  intent: Intent;
  confidence: number;
  subIntent?: string;
  reasoning?: string;
}

/**
 * User model tracked by modelsTheUser subprocess
 */
export interface UserModel {
  /** User's name if known */
  name: string;
  /** Areas of expertise observed */
  expertise: string[];
  /** Communication preferences */
  preferences: {
    communicationStyle: 'brief' | 'detailed';
    technicalLevel: 'novice' | 'intermediate' | 'expert';
  };
  /** Topics discussed recently */
  recentTopics: string[];
  /** Last update timestamp */
  lastUpdated: string;
}

/**
 * System health metrics for guardian process
 */
export interface SystemHealthReport {
  // Hardware metrics
  cpuUsage: number;
  memoryUsage: number;
  gpuUsage: number;
  thermalLevel: 'normal' | 'elevated' | 'critical';
  currentTemp?: number;
  diskIO: { readsPerSec: number; writesPerSec: number };
  networkAvailable: boolean;
  topProcesses: { pid: number; name: string; cpu: number; memory: number }[];
  issues: string[];
  timestamp: string;

  // Workspace environment (optional -- graceful when tools unavailable)
  devServers?: { name: string; url: string; pid: number }[];
  browserTabs?: { id: string; title: string; url: string }[];
  processByCategory?: Record<string, { count: number; totalCpu: number; totalMem: number }>;
}

/**
 * Daimonic whisper from the observer subprocess
 */
export interface DaimonicWhisper {
  content: string;
  timestamp: string;
  influence?: 'subtle' | 'moderate' | 'strong';
}

/**
 * Subprocess configuration for ProcessRunner
 */
export interface SubprocessConfig {
  /** Subprocess name for logging */
  name: string;
  /** The subprocess function */
  process: MentalProcess;
  /** Whether subprocess is enabled */
  enabled: boolean;
  /** If true, can run in parallel with other independent subprocesses (default: true) */
  independent?: boolean;
  /** Optional condition to check before running */
  runCondition?: (context: MentalProcessContext) => boolean;
}

/**
 * ProcessRunner configuration
 */
export interface ProcessRunnerConfig {
  /** Main mental process (entry point) */
  mainProcess: MentalProcess;
  /** Subprocesses to run alongside */
  subprocesses: SubprocessConfig[];
  /** Session ID */
  sessionId: string;
  /** Optional process loader for DI — allows per-soul process registries */
  loadProcess?: (name: string) => Promise<MentalProcess | null>;
}

/**
 * Dispatch action types for UI/external systems
 */
export type DispatchActionType =
  | 'intentClassified'
  | 'emotionalStateChanged'
  | 'daimonicWhisper'
  | 'systemAlert'
  | 'userModelUpdated'
  | 'processTransition'
  | 'suggestClaudeCode'
  | 'memoryWritten'
  | 'dreamModel'
  | 'dreamScene'
  | 'dreamWake'
  | 'tweetDrafted'
  | 'tweetPosted';

/**
 * Memory types for persistent markdown memories
 */
export type MemoryType = 'episodic' | 'conceptual' | 'personal';

/**
 * A memory entry to be written to disk
 */
export interface MemoryEntry {
  type: MemoryType;
  title: string;
  content: string;
  tags: string[];
  participants: string[];
  date: string;
}

/**
 * Dream state tracked during sleeping hours
 */
export interface DreamState {
  /** Current dream plot (markdown), empty when not dreaming */
  dreamModel: string;
  /** 0=awake, 1=dreaming */
  dreamTime: 0 | 1;
  /** Scene counter within a dream cycle */
  melatoninCounter: number;
}

/**
 * Archived dream summary
 */
export interface DreamHistoryEntry {
  dreamId: string;
  summary: string;
  date: string;
  themes: string[];
}

/**
 * Scheduled event types
 */
export type ScheduledEventType =
  | 'idleCheck'
  | 'systemHealthCheck'
  | 'dreamStateCheck';
