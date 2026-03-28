/**
 * Home Assistant API service for fetching entities
 * 
 * In development: Requests go through Vite proxy to actual HA instance
 * In production: Backend API handles these endpoints
 */

export interface HAConnectionConfig {
  host?: string | null
  port?: number | null
  token?: string | null
  protocol?: 'http' | 'https' | null
}

export interface HAEntity {
  entity_id: string
  state: string
  attributes: {
    friendly_name?: string
    unit_of_measurement?: string
    [key: string]: any
  }
  last_changed: string
  last_updated: string
}

export interface HAEntityOption {
  entity_id: string
  friendly_name: string
  state: string
  unit?: string
  domain: string
}

// In-memory cache for entities (session-based)
let entityCache: HAEntityOption[] | null = null
let cacheTimestamp: number = 0
const CACHE_DURATION = 5 * 60 * 1000 // 5 minutes

/**
 * Resolve secret values in token
 * Handles "!secret key_name" format by looking up in secrets
 */
function resolveToken(token: string | null | undefined, secrets: Record<string, string>): string | null {
  if (!token) return null
  
  const secretPattern = /^!secret\s+(\S+)$/
  const match = token.match(secretPattern)
  
  if (match) {
    const secretKey = match[1]
    return secrets[secretKey] || null
  }
  
  return token
}

/**
 * Fetch all entities from Home Assistant via backend API
 * 
 * @param apiEndpoint - Relative API endpoint (e.g., '/api/ha/states')
 * @param config - HA connection config (passed to backend)
 * @param secrets - Secrets for resolving !secret references
 */
export async function fetchHAEntities(
  apiEndpoint: string,
  config: HAConnectionConfig,
  secrets: Record<string, string> = {}
): Promise<HAEntityOption[]> {
  const token = resolveToken(config.token, secrets)
  
  if (!token) {
    throw new Error('Home Assistant token not configured. Please configure hasstoken in HASS settings.')
  }
  
  try {
    // Use relative URL - in dev: proxied by Vite, in prod: handled by backend
    const url = new URL(apiEndpoint, window.location.origin)
    
    // Pass HA connection config via headers (backend will use to connect to HA)
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }
    
    if (config.host) headers['X-HA-Host'] = config.host
    if (config.port) headers['X-HA-Port'] = String(config.port)
    if (config.protocol) headers['X-HA-Protocol'] = config.protocol
    if (token) headers['X-HA-Token'] = token
    
    const response = await fetch(url.toString(), {
      method: 'GET',
      headers,
    })
    
    if (!response.ok) {
      if (response.status === 401) {
        throw new Error('Unauthorized: Invalid Home Assistant token')
      }
      const errorText = await response.text().catch(() => response.statusText)
      throw new Error(`API error: ${response.status} - ${errorText}`)
    }
    
    const entities: HAEntity[] = await response.json()
    
    // Transform to our format
    const options: HAEntityOption[] = entities.map(entity => ({
      entity_id: entity.entity_id,
      friendly_name: entity.attributes.friendly_name || entity.entity_id,
      state: entity.state,
      unit: entity.attributes.unit_of_measurement,
      domain: entity.entity_id.split('.')[0]
    }))
    
    // Update cache
    entityCache = options
    cacheTimestamp = Date.now()
    
    return options
  } catch (error) {
    if (error instanceof TypeError && error.message.includes('fetch')) {
      throw new Error(`Network error: Cannot connect to API. Check if server is running.`)
    }
    throw error
  }
}

/**
 * Get cached entities if available and fresh
 */
export function getCachedEntities(): HAEntityOption[] | null {
  if (!entityCache) return null
  
  const age = Date.now() - cacheTimestamp
  if (age > CACHE_DURATION) {
    entityCache = null
    return null
  }
  
  return entityCache
}

/**
 * Clear the entity cache (useful for forcing refresh)
 */
export function clearEntityCache(): void {
  entityCache = null
  cacheTimestamp = 0
}

/**
 * Filter entities by domain(s)
 * @param entities List of entities
 * @param domainFilter Comma-separated domain list (e.g., "sensor,input_number")
 */
export function filterEntitiesByDomain(
  entities: HAEntityOption[],
  domainFilter?: string
): HAEntityOption[] {
  let filtered = entities
  
  // Filter by domain if specified
  if (domainFilter) {
    const domains = domainFilter.split(',').map(d => d.trim().toLowerCase())
    filtered = filtered.filter(entity => domains.includes(entity.domain))
  }
  
  return filtered
}

/**
 * Group entities by domain for organized display
 */
export function groupEntitiesByDomain(
  entities: HAEntityOption[]
): Record<string, HAEntityOption[]> {
  const groups: Record<string, HAEntityOption[]> = {}
  
  entities.forEach(entity => {
    if (!groups[entity.domain]) {
      groups[entity.domain] = []
    }
    groups[entity.domain].push(entity)
  })
  
  // Sort entities within each group by entity_id
  Object.keys(groups).forEach(domain => {
    groups[domain].sort((a, b) => a.entity_id.localeCompare(b.entity_id))
  })
  
  return groups
}

/**
 * Format entity for display in dropdown
 */
export function formatEntityLabel(entity: HAEntityOption): string {
  let label = entity.entity_id
  
  if (entity.friendly_name && entity.friendly_name !== entity.entity_id) {
    label += ` - ${entity.friendly_name}`
  }
  
  if (entity.state && entity.state !== 'unknown' && entity.state !== 'unavailable') {
    label += ` (${entity.state}`
    if (entity.unit) {
      label += ` ${entity.unit}`
    }
    label += ')'
  }
  
  return label
}
