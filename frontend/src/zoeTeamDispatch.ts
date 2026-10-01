import { createHash } from 'node:crypto'

type RecordValue = Record<string, unknown>
type Dispatch = (type: string, payload?: RecordValue) => Promise<unknown>
type DurableSubmit = (command: 'lab.v1.submit', payload: RecordValue, requestId: string) => Promise<unknown>

export function remoteTeamRequestId(channel: string, messageId: string): string {
  return `zoe-team:${createHash('sha256').update(JSON.stringify([channel, messageId])).digest('hex')}`
}

// The existing HTTP bridge authenticates Zoe. Zoe must verify the original
// human sender before invoking this route. Peer replies are never owner orders.
export function createZoeTeamDispatch(dispatch: Dispatch, submit: DurableSubmit): Dispatch {
  return async (type, params) => {
    if (type !== 'zoe-remote-command' || !params || !('kind' in params)) return dispatch(type, params)
    const { kind, channel, message_id: messageId, objective } = params
    const invalid = Object.keys(params).some(key => !['kind', 'channel', 'message_id', 'objective'].includes(key))
      || kind !== 'team-mission' || typeof channel !== 'string' || !['whatsapp', 'muse'].includes(channel)
      || typeof messageId !== 'string' || !messageId.trim() || messageId.length > 160
      || typeof objective !== 'string' || !objective.trim() || objective.length > 4000
    if (invalid) return { success: false, accepted: false, state: 'REJECTED', code: 'INVALID_REMOTE_MISSION', mission_complete: false }
    const requestId = remoteTeamRequestId(String(channel), messageId as string)
    try {
      const receipt = await submit('lab.v1.submit', { objective: (objective as string).trim() }, requestId) as RecordValue | null
      const confirmed = receipt?.success === true && receipt.accepted === true && receipt.confirmed === true
        && typeof receipt.operation_id === 'string' && !!receipt.operation_id
      return {
        ...receipt,
        success: confirmed,
        delivery: confirmed ? 'DISPATCH_AUTHORIZED' : 'UNCONFIRMED',
        mission_complete: false,
        request_id: requestId,
        reply_to_message_id: messageId,
      }
    } catch {
      // Same original message ID may be retried safely against the durable
      // ledger. Never invent another ID after a timeout or execute twice here.
      return { success: false, accepted: false, delivery: 'UNCONFIRMED', mission_complete: false,
        code: 'REMOTE_MISSION_OUTCOME_UNKNOWN', request_id: requestId, reply_to_message_id: messageId }
    }
  }
}
