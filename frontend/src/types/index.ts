// 与后端实际返回结构一一对应（字段名以 FastAPI 的 JSON 输出为准）

export interface AuthUser {
  id: number
  username: string
  is_admin: boolean
}

/**
 * 节点配置：各协议自由形态的 JSON，字段随协议不同（vless 有 tls.reality，
 * hysteria2 有 obfs，shadowsocks 只有 method/password …）。
 * 这里刻意用宽松类型：要精确表达就得为 8 个协议各写一个联合分支，
 * 而表单是按后端下发的 fields 描述动态读写的，收紧收益不抵成本。
 */
export type NodeConfig = Record<string, any>

export interface Node {
  id: number
  name: string
  type: string
  server: string
  server_port: number
  enabled: boolean
  config: NodeConfig
  created_at?: string
  updated_at?: string
}

export interface Subscription {
  id: number
  user_id: number
  name: string
  /** 订阅访问凭据，拼下载链接用；不可枚举 */
  token: string
  slug: string
  /** 为空表示包含全部节点 */
  node_ids: number[]
  enabled: boolean
  created_at?: string
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
  /** 列表里显示的短码，由后端注册表提供，前端不再自己维护 */
  abbr: string
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
  /** 后端在探测不到版本时返回 */
  error?: string
}

/** GET /api/stats —— 顶部统计卡数据 */
export interface Stats {
  total_nodes?: number
  active_nodes?: number
  total_subs?: number
  active_subs?: number
}

/** GET /api/server-info */
export interface ServerInfo {
  server_ip: string
}

export interface MessageResponse {
  message: string
}

export interface UpdateResponse {
  message: string
  version?: string | null
  log?: string[]
}
