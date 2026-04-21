/**
 * Small pill/badge indicating WebSocket connection status.
 */
import type { WsStatus } from '../hooks/useOpWebSocket'
import styles from './WsStatusIndicator.module.css'

interface Props {
  status: WsStatus
  reconnectIn: number | null
  onReconnect: () => void
}

export default function WsStatusIndicator({ status, reconnectIn, onReconnect }: Props) {
  if (status === 'connected') {
    return (
      <div className={`${styles.pill} ${styles.connected}`}>
        <span className={styles.dot} />
        <span className={styles.label}>Live</span>
      </div>
    )
  }

  if (status === 'connecting') {
    return (
      <div className={`${styles.pill} ${styles.connecting}`}>
        <span className={styles.dot} />
        <span className={styles.label}>
          {reconnectIn != null && reconnectIn > 0
            ? `Reconnecting in ${reconnectIn}s`
            : 'Connecting…'}
        </span>
      </div>
    )
  }

  // disconnected
  return (
    <div className={`${styles.pill} ${styles.disconnected}`}>
      <span className={styles.dot} />
      <span className={styles.label}>Disconnected</span>
      <button className={styles.reconnectBtn} onClick={onReconnect}>
        Reconnect
      </button>
    </div>
  )
}
