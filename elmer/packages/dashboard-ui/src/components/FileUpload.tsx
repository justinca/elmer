import { useDropzone } from "react-dropzone"
import { cn } from "@/lib/utils"
import { Upload, FileAudio, X } from "lucide-react"
import { Progress } from "@/components/ui/progress"
import { Button } from "@/components/ui/button"
import { useState } from "react"

interface FileUploadProps {
  accept?: Record<string, string[]>
  onUpload: (file: File) => Promise<void>
  maxSize?: number
  label?: string
  formats?: string
  className?: string
}

export function FileUpload({
  accept,
  onUpload,
  maxSize = 100 * 1024 * 1024,
  label = "Drop files here or click to browse",
  formats,
  className,
}: FileUploadProps) {
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept,
    maxSize,
    multiple: false,
    onDrop: (accepted) => {
      if (accepted.length > 0) {
        setFile(accepted[0])
        setError(null)
      }
    },
    onDropRejected: (rejections) => {
      const msg = rejections[0]?.errors[0]?.message || "File rejected"
      setError(msg)
    },
  })

  const handleUpload = async () => {
    if (!file) return
    setUploading(true)
    setProgress(10)
    try {
      const interval = setInterval(() => {
        setProgress((p) => Math.min(p + 15, 90))
      }, 500)
      await onUpload(file)
      clearInterval(interval)
      setProgress(100)
      setTimeout(() => {
        setFile(null)
        setProgress(0)
        setUploading(false)
      }, 1000)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed")
      setUploading(false)
      setProgress(0)
    }
  }

  const clear = () => {
    setFile(null)
    setError(null)
    setProgress(0)
  }

  return (
    <div className={cn("space-y-3", className)}>
      <div
        {...getRootProps()}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 transition-colors",
          isDragActive
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/25 hover:border-primary/50",
          uploading && "pointer-events-none opacity-50",
        )}
      >
        <input {...getInputProps()} />
        <Upload className="mb-2 h-8 w-8 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">{label}</p>
        {formats && (
          <p className="mt-1 text-xs text-muted-foreground/70">{formats}</p>
        )}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {file && (
        <div className="flex items-center gap-3 rounded-md border p-3">
          <FileAudio className="h-5 w-5 shrink-0 text-muted-foreground" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{file.name}</p>
            <p className="text-xs text-muted-foreground">
              {(file.size / 1024 / 1024).toFixed(1)} MB
            </p>
          </div>
          {!uploading && (
            <>
              <Button size="sm" onClick={handleUpload}>
                Upload
              </Button>
              <button onClick={clear} className="text-muted-foreground hover:text-foreground">
                <X className="h-4 w-4" />
              </button>
            </>
          )}
        </div>
      )}

      {uploading && <Progress value={progress} className="h-2" />}
    </div>
  )
}
