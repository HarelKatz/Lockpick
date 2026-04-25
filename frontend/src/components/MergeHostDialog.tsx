/**
 * MergeHostDialog — pick a target host and resolve nickname/comment/status
 * conflicts before merging the source into it. Mirrors EditModal's shell;
 * heavy lifting is in <MergeHostForm/> below.
 */
import { useMemo, useState } from 'react'
import EditModal from './EditModal'
import editStyles from './EditModal.module.css'
import styles from './MergeHostDialog.module.css'
import { mergeHost } from '../api/hosts'
import { ApiError } from '../api/client'
import type { Host, MergeHostRequest, MergeResolutions } from '../types'

interface Props {
  source: Host
  targetCandidate?: Host | null
  allHosts: Host[]
  onClose: () => void
  onMerged: (target: Host) => void
}

type Choice = 'source' | 'target' | 'custom'

interface ConflictState {
  nickname: { choice: Choice; custom: string }
  comment: { choice: Choice; custom: string }
  status: { choice: 'source' | 'target' }
}

function initialState(): ConflictState {
  // Default everywhere is to keep target's value — a no-op merge if the user
  // doesn't change anything is the safest behavior.
  return {
    nickname: { choice: 'target', custom: '' },
    comment: { choice: 'target', custom: '' },
    status: { choice: 'target' },
  }
}

function buildResolutions(
  state: ConflictState,
  conflicts: { nickname: boolean; comment: boolean; status: boolean },
): MergeResolutions {
  const r: MergeResolutions = {}
  if (conflicts.nickname) {
    if (state.nickname.choice === 'source') r.nickname = 'source'
    else if (state.nickname.choice === 'custom') r.nickname = state.nickname.custom
    // 'target' = no key, server keeps target's value
  }
  if (conflicts.comment) {
    if (state.comment.choice === 'source') r.comment = 'source'
    else if (state.comment.choice === 'custom') r.comment = state.comment.custom
  }
  if (conflicts.status) {
    if (state.status.choice === 'source') r.status = 'source'
  }
  return r
}

export default function MergeHostDialog(props: Props) {
  return (
    <EditModal title={`Merge '${props.source.nickname}' into…`} onClose={props.onClose}>
      <MergeHostForm {...props} />
    </EditModal>
  )
}

function MergeHostForm({ source, targetCandidate, allHosts, onClose, onMerged }: Props) {
  const [targetId, setTargetId] = useState<string>(targetCandidate?.id ?? '')
  const [state, setState] = useState<ConflictState>(initialState)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const target = useMemo(
    () => allHosts.find(h => h.id === targetId) ?? null,
    [allHosts, targetId],
  )

  const conflicts = useMemo(() => {
    if (!target) return { nickname: false, comment: false, status: false }
    const both = (a: string | null | undefined, b: string | null | undefined) =>
      a != null && b != null && a !== b
    return {
      nickname: both(source.nickname, target.nickname),
      comment: both(source.comment, target.comment),
      status: both(source.status, target.status),
    }
  }, [source, target])

  // Disable submit if a custom-radio is picked but its text input is empty —
  // empty nicknames in particular create confusing UX downstream.
  const customEmpty =
    (conflicts.nickname && state.nickname.choice === 'custom' && state.nickname.custom.trim() === '') ||
    (conflicts.comment && state.comment.choice === 'custom' && state.comment.custom.trim() === '')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!target || submitting) return
    setSubmitting(true)
    setError(null)
    const body: MergeHostRequest = {
      target_host_id: target.id,
      resolutions: buildResolutions(state, conflicts),
    }
    try {
      const resp = await mergeHost(source.id, body)
      onMerged(resp.target)
      onClose()
    } catch (err) {
      const detail =
        err instanceof ApiError && err.body && typeof err.body === 'object' && 'detail' in err.body
          ? String((err.body as { detail: unknown }).detail)
          : err instanceof Error
          ? err.message
          : 'Merge failed'
      setError(detail)
      setSubmitting(false)
    }
  }

  return (
    <form className={editStyles.form} onSubmit={handleSubmit}>
      <div className={editStyles.field}>
        <label htmlFor="merge-target">Target host</label>
        <select
          id="merge-target"
          value={targetId}
          onChange={e => setTargetId(e.target.value)}
          disabled={submitting}
        >
          <option value="">— Select a host —</option>
          {allHosts
            .filter(h => h.id !== source.id)
            .map(h => (
              <option key={h.id} value={h.id}>
                {h.nickname}
              </option>
            ))}
        </select>
        <span className={editStyles.fieldHint}>
          The source host '{source.nickname}' will be deleted; all of its
          relations move to the target.
        </span>
      </div>

      {target && conflicts.nickname && (
        <ConflictRow
          label="Nickname"
          sourceValue={source.nickname}
          targetValue={target.nickname}
          choice={state.nickname.choice}
          custom={state.nickname.custom}
          allowCustom
          onChoice={choice =>
            setState(s => ({ ...s, nickname: { ...s.nickname, choice } }))
          }
          onCustom={custom =>
            setState(s => ({ ...s, nickname: { ...s.nickname, custom } }))
          }
        />
      )}
      {target && conflicts.comment && (
        <ConflictRow
          label="Comment"
          sourceValue={source.comment ?? ''}
          targetValue={target.comment ?? ''}
          choice={state.comment.choice}
          custom={state.comment.custom}
          allowCustom
          onChoice={choice =>
            setState(s => ({ ...s, comment: { ...s.comment, choice } }))
          }
          onCustom={custom =>
            setState(s => ({ ...s, comment: { ...s.comment, custom } }))
          }
        />
      )}
      {target && conflicts.status && (
        <ConflictRow
          label="Status"
          sourceValue={source.status ?? ''}
          targetValue={target.status ?? ''}
          choice={state.status.choice}
          custom=""
          allowCustom={false}
          onChoice={choice =>
            setState(s => ({ ...s, status: { choice: choice as 'source' | 'target' } }))
          }
          onCustom={() => {}}
        />
      )}
      {target &&
        !conflicts.nickname &&
        !conflicts.comment &&
        !conflicts.status && (
          <p className={editStyles.fieldHint}>
            No field conflicts — the target host keeps its current
            nickname, comment, and status.
          </p>
        )}

      {error && <p className={editStyles.error}>{error}</p>}

      <div className={editStyles.actions}>
        <button
          type="button"
          className={editStyles.btnSecondary}
          onClick={onClose}
          disabled={submitting}
        >
          Cancel
        </button>
        <button
          type="submit"
          className={styles.btnDanger}
          disabled={!target || submitting || customEmpty}
        >
          {submitting ? 'Merging…' : 'Merge'}
        </button>
      </div>
    </form>
  )
}

interface ConflictRowProps {
  label: string
  sourceValue: string
  targetValue: string
  choice: Choice
  custom: string
  allowCustom: boolean
  onChoice: (choice: Choice) => void
  onCustom: (value: string) => void
}

function ConflictRow({
  label,
  sourceValue,
  targetValue,
  choice,
  custom,
  allowCustom,
  onChoice,
  onCustom,
}: ConflictRowProps) {
  const id = `merge-${label.toLowerCase()}`
  return (
    <fieldset className={styles.conflict}>
      <legend className={styles.conflictLegend}>{label}</legend>
      <label className={styles.choice}>
        <input
          type="radio"
          name={id}
          checked={choice === 'source'}
          onChange={() => onChoice('source')}
        />
        <span className={styles.choiceLabel}>{sourceValue || <em>none</em>}</span>
        <span className={styles.choiceTag}>source</span>
      </label>
      <label className={styles.choice}>
        <input
          type="radio"
          name={id}
          checked={choice === 'target'}
          onChange={() => onChoice('target')}
        />
        <span className={styles.choiceLabel}>{targetValue || <em>none</em>}</span>
        <span className={styles.choiceTag}>target</span>
      </label>
      {allowCustom && (
        <label className={styles.choice}>
          <input
            type="radio"
            name={id}
            checked={choice === 'custom'}
            onChange={() => onChoice('custom')}
          />
          <input
            type="text"
            className={styles.customInput}
            value={custom}
            placeholder="Custom value…"
            onChange={e => onCustom(e.target.value)}
            onFocus={() => onChoice('custom')}
            disabled={choice !== 'custom'}
          />
          <span className={styles.choiceTag}>custom</span>
        </label>
      )}
    </fieldset>
  )
}
