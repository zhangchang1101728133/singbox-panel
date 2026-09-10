export interface AuthUser {
  username: string
}

export interface Node {
  id: string
  name: string
  server: string
  port: number
  type: string
  [key: string]: unknown
}

export interface Subscription {
  id: string
  name: string
  url: string
  nodes?: Node[]
  updated_at?: string
}

export interface ProtocolField {
  key: string
  label: string
  type: 'text' | 'number' | 'bool' | 'select'
  default?: unknown
  options?: string[]
  gen?: 'uuid' | 'password'
}

export interface Protocol {
  id: string
  label: string
  default_port: number
  min_version: string | null
  available: boolean
  fields: ProtocolField[]
}

export interface ProtocolsResponse {
  core_version: string | null
  protocols: Protocol[]
}

export interface SingboxVersion {
  version: string | null
  latest_version: string | null
  update_available: boolean
  image: string
  container: string
  running: boolean
  compose_available: boolean
  error?: string
}

export interface ApiError extends Error {
  status?: number
}
