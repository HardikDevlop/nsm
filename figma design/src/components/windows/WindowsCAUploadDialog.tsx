import { useRef, useState } from "react"
import GlassCard from "../GlassCard"
import { uploadWindowsCABundle } from "../../lib/api"

type Props = { siteId: number; onUploaded: () => void; onClose: () => void }
const MAX_BYTES = 1024 * 1024

export default function WindowsCAUploadDialog({ siteId, onUploaded, onClose }: Props) {
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState("")
  const [uploading, setUploading] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const close = () => {
    if (uploading) return
    setName(""); setDescription(""); setFile(null); setError("")
    if (fileInput.current) fileInput.current.value = ""
    onClose()
  }
  const submit = async () => {
    if (!name.trim()) return setError("Certificate name is required.")
    if (!file) return setError("Certificate file is required.")
    if (file.size > MAX_BYTES) return setError("Certificate file must not exceed 1 MiB.")
    setUploading(true); setError("")
    try {
      const formData = new FormData()
      formData.set("site_id", String(siteId)); formData.set("name", name.trim())
      if (description.trim()) formData.set("description", description.trim())
      formData.set("certificate", file)
      await uploadWindowsCABundle(formData)
      onUploaded()
      close()
    } catch {
      setError("Unable to upload the Windows CA certificate.")
    } finally { setUploading(false) }
  }
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-label="Upload Windows CA certificate">
    <GlassCard className="w-full max-w-lg p-5">
      <div className="flex items-start justify-between gap-3"><div><h2 className="font-display font-bold" style={{ color: "var(--t-text)" }}>UPLOAD WINDOWS CA</h2><p className="mt-1 font-mono text-xs" style={{ color: "var(--t-muted)" }}>Site ID {siteId}</p></div><button type="button" onClick={close} disabled={uploading} aria-label="Close upload dialog" className="font-mono text-xs disabled:opacity-50">✕</button></div>
      <div className="mt-5 space-y-4">
        <label className="block font-mono text-xs" style={{ color: "var(--t-muted)" }}>Certificate name<input value={name} onChange={(event) => setName(event.target.value)} disabled={uploading} className="mt-1 w-full rounded-lg border px-3 py-2" /></label>
        <label className="block font-mono text-xs" style={{ color: "var(--t-muted)" }}>Description <span>(optional)</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} disabled={uploading} className="mt-1 w-full rounded-lg border px-3 py-2" /></label>
        <label className="block font-mono text-xs" style={{ color: "var(--t-muted)" }}>PEM certificate<input ref={fileInput} type="file" accept=".pem,.crt,.cer,application/x-pem-file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} disabled={uploading} className="mt-1 block w-full text-xs" /></label>
        {file && <p className="font-mono text-[10px]" style={{ color: "var(--t-muted)" }}>{file.name} · {file.size} bytes</p>}
        {error && <p role="alert" className="font-mono text-xs" style={{ color: "var(--t-danger, #ff6688)" }}>⚠ {error}</p>}
      </div>
      <div className="mt-5 flex justify-end gap-2"><button type="button" onClick={close} disabled={uploading} className="rounded-lg border px-3 py-2 font-mono text-xs disabled:opacity-50">CANCEL</button><button type="button" onClick={() => void submit()} disabled={uploading} className="rounded-lg px-3 py-2 font-mono text-xs disabled:opacity-50" style={{ background: "var(--t-accent)", color: "var(--t-bg)" }}>{uploading ? "UPLOADING…" : "UPLOAD"}</button></div>
    </GlassCard>
  </div>
}
