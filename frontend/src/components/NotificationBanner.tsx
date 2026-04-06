import styles from './NotificationBanner.module.css'

interface Props {
  delta: number
  onRefresh: () => void
}

export default function NotificationBanner({ delta, onRefresh }: Props) {
  if (delta <= 0) return null
  return (
    <div className={styles.banner} role="alert">
      <span className={styles.message}>
        {delta} new record{delta !== 1 ? 's' : ''} since your last refresh
      </span>
      <button className={styles.refreshBtn} onClick={onRefresh}>
        Refresh
      </button>
    </div>
  )
}
