/**
 * Sweetalert2 theme wrapper — dark glass style matching NMS design system.
 * Import { toast, confirm, alert } from here everywhere in the app.
 */
import Swal from 'sweetalert2'

/* ── Dark glass theme ───────────────────────────────────────────────────── */
const BASE = {
  background:   'rgba(8, 18, 40, 0.97)',
  color:        '#c8d8ee',
  confirmButtonColor: '#00d4ff',
  cancelButtonColor:  'rgba(255,255,255,0.08)',
  customClass: {
    popup:         'swal-glass-popup',
    title:         'swal-glass-title',
    htmlContainer: 'swal-glass-html',
    confirmButton: 'swal-glass-confirm',
    cancelButton:  'swal-glass-cancel',
  },
}

/* Inject CSS once */
if (typeof document !== 'undefined') {
  const styleId = 'swal-glass-styles'
  if (!document.getElementById(styleId)) {
    const s = document.createElement('style')
    s.id = styleId
    s.textContent = `
      .swal-glass-popup {
        border: 1px solid rgba(0,212,255,0.25) !important;
        border-radius: 14px !important;
        backdrop-filter: blur(20px) !important;
        box-shadow: 0 0 40px rgba(0,212,255,0.12), 0 8px 32px rgba(0,0,0,0.6) !important;
        font-family: 'JetBrains Mono', monospace !important;
      }
      .swal-glass-title {
        color: #00d4ff !important;
        font-family: 'Space Grotesk', sans-serif !important;
        font-weight: 700 !important;
        font-size: 1.1rem !important;
        letter-spacing: 0.05em !important;
      }
      .swal-glass-html {
        color: #8899bb !important;
        font-size: 0.78rem !important;
        font-family: 'JetBrains Mono', monospace !important;
      }
      .swal-glass-confirm {
        background: rgba(0,212,255,0.18) !important;
        border: 1px solid rgba(0,212,255,0.45) !important;
        color: #00d4ff !important;
        border-radius: 8px !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.78rem !important;
        padding: 8px 20px !important;
        font-weight: 600 !important;
        letter-spacing: 0.05em !important;
        box-shadow: none !important;
      }
      .swal-glass-confirm:hover {
        background: rgba(0,212,255,0.28) !important;
      }
      .swal-glass-cancel {
        background: rgba(255,255,255,0.06) !important;
        border: 1px solid rgba(255,255,255,0.12) !important;
        color: #8899bb !important;
        border-radius: 8px !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.78rem !important;
        padding: 8px 20px !important;
        box-shadow: none !important;
      }
      .swal-glass-cancel:hover {
        background: rgba(255,255,255,0.10) !important;
        color: #c8d8ee !important;
      }
      /* Danger confirm button */
      .swal-glass-confirm-danger {
        background: rgba(255,51,102,0.18) !important;
        border: 1px solid rgba(255,51,102,0.45) !important;
        color: #ff3366 !important;
        border-radius: 8px !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.78rem !important;
        padding: 8px 20px !important;
        font-weight: 600 !important;
        box-shadow: none !important;
      }
      .swal-glass-confirm-danger:hover {
        background: rgba(255,51,102,0.28) !important;
      }
      /* Toast container */
      .swal-glass-toast {
        border: 1px solid rgba(0,212,255,0.2) !important;
        border-radius: 10px !important;
        font-family: 'JetBrains Mono', monospace !important;
        box-shadow: 0 4px 24px rgba(0,0,0,0.5) !important;
        height: auto !important;
        min-height: 0 !important;
      }
      /* Toasts use SweetAlert's full-viewport container internally. Keep that
         implementation detail from becoming a visible full-screen popup. */
      .swal-glass-toast-container {
        background: transparent !important;
        min-height: 0 !important;
        height: auto !important;
        pointer-events: none !important;
      }
      .swal-glass-toast-container .swal-glass-toast {
        pointer-events: auto !important;
      }
      /* SweetAlert keeps toast containers fixed to the viewport. The wrapper
         must remain layout-only; only the toast itself should be visible. */
      .swal2-container.swal2-top-end:has(.swal2-toast) {
        background: transparent !important;
        min-height: 0 !important;
        height: auto !important;
        pointer-events: none !important;
      }
      .swal2-container.swal2-top-end:has(.swal2-toast) .swal2-toast {
        pointer-events: auto !important;
        height: auto !important;
        min-height: 0 !important;
      }
    `
    document.head.appendChild(s)
  }
}

/* ── Toast (small corner notification) ──────────────────────────────────── */
const Toast = Swal.mixin({
  ...BASE,
  toast: true,
  position: 'top-end',
  showConfirmButton: false,
  timer: 3000,
  timerProgressBar: true,
  customClass: {
    ...BASE.customClass,
    popup: 'swal-glass-toast swal-glass-popup',
  },
  didOpen: (toast) => {
    toast.closest('.swal2-container')?.classList.add('swal-glass-toast-container')
    toast.addEventListener('mouseenter', Swal.stopTimer)
    toast.addEventListener('mouseleave', Swal.resumeTimer)
  },
})

export const toast = {
  success: (msg: string) =>
    Toast.fire({ icon: 'success', title: msg, background: 'rgba(8,25,55,0.97)', color: '#00ff88' }),

  error: (msg: string) =>
    Toast.fire({ icon: 'error', title: msg, background: 'rgba(8,25,55,0.97)', color: '#ff3366' }),

  info: (msg: string) =>
    Toast.fire({ icon: 'info', title: msg, background: 'rgba(8,25,55,0.97)', color: '#00d4ff' }),

  warning: (msg: string) =>
    Toast.fire({ icon: 'warning', title: msg, background: 'rgba(8,25,55,0.97)', color: '#ffaa00' }),
}

/* ── Confirm dialog ──────────────────────────────────────────────────────── */
export async function confirmDanger(opts: {
  title: string
  text?: string
  confirmText?: string
}): Promise<boolean> {
  const result = await Swal.fire({
    ...BASE,
    title: opts.title,
    html: opts.text
      ? `<span style="color:#8899bb;font-size:0.8rem">${opts.text}</span>`
      : undefined,
    icon: 'warning',
    iconColor: '#ff3366',
    showCancelButton: true,
    confirmButtonText: opts.confirmText ?? 'Delete',
    cancelButtonText: 'Cancel',
    reverseButtons: true,
    customClass: {
      ...BASE.customClass,
      confirmButton: 'swal-glass-confirm-danger',
    },
  })
  return result.isConfirmed
}

export async function confirmAction(opts: {
  title: string
  text?: string
  confirmText?: string
}): Promise<boolean> {
  const result = await Swal.fire({
    ...BASE,
    title: opts.title,
    html: opts.text
      ? `<span style="color:#8899bb;font-size:0.8rem">${opts.text}</span>`
      : undefined,
    icon: 'question',
    iconColor: '#00d4ff',
    showCancelButton: true,
    confirmButtonText: opts.confirmText ?? 'Confirm',
    cancelButtonText: 'Cancel',
    reverseButtons: true,
  })
  return result.isConfirmed
}

export async function promptText(opts: {
  title: string
  text?: string
  inputLabel?: string
  inputValue?: string
  confirmText?: string
  trim?: boolean
  allowWhitespace?: boolean
}): Promise<string | null> {
  const result = await Swal.fire({
    ...BASE,
    title: opts.title,
    html: opts.text
      ? `<span style="color:#8899bb;font-size:0.8rem">${opts.text}</span>`
      : undefined,
    input: 'text',
    inputLabel: opts.inputLabel,
    inputValue: opts.inputValue ?? '',
    inputAttributes: {
      autocapitalize: 'off',
      autocomplete: 'off',
    },
    showCancelButton: true,
    confirmButtonText: opts.confirmText ?? 'Save',
    cancelButtonText: 'Cancel',
    reverseButtons: true,
  })
  if (!result.isConfirmed) return null
  const rawValue = typeof result.value === 'string' ? result.value : ''
  if (rawValue === '') return null
  const value = opts.trim === false ? rawValue : rawValue.trim()
  if (!opts.allowWhitespace && value.trim() === '') return null
  return value === '' ? null : value
}
