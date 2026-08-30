import { useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { REASON_CODE_LABELS } from '@/lib/labels'
import { REASON_CODES, type ReasonCode } from '@/types/decision'

/**
 * Ablehnen mit Pflichtgrund (Spec Sprint 5, Aufgabe 3, Punkt 8).
 *
 * Ohne `reason_code` ist der Knopf gesperrt: eine Ablehnung ohne Grund ist für den
 * nächsten Lauf und für den Kunden wertlos. Der Freitext ist freiwillig.
 */
export function RejectDialog({
  open,
  onOpenChange,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: (reasonCode: ReasonCode, reason: string) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Finding ablehnen</DialogTitle>
          <DialogDescription>
            Der Grund wird mit exportiert und erklärt im nächsten Lauf, warum das Finding
            bestehen bleibt.
          </DialogDescription>
        </DialogHeader>
        {/* Eigene Komponente: der Inhalt wird beim Schließen abgeräumt und beginnt
            damit ohne den Grund des vorigen Findings. */}
        <RejectForm onCancel={() => onOpenChange(false)} onConfirm={onConfirm} />
      </DialogContent>
    </Dialog>
  )
}

function RejectForm({
  onCancel,
  onConfirm,
}: {
  onCancel: () => void
  onConfirm: (reasonCode: ReasonCode, reason: string) => void
}) {
  const [reasonCode, setReasonCode] = useState<ReasonCode | null>(null)
  const [reason, setReason] = useState('')

  return (
    <>
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Grund (Pflicht)
          {/* Leerer Wert statt `undefined`: Radix zeigt dann den Platzhalter und die
              Auswahl ist von Anfang an kontrolliert. */}
          <Select
            value={reasonCode ?? ''}
            onValueChange={(value) => setReasonCode(value as ReasonCode)}
          >
            <SelectTrigger className="w-full text-sm">
              <SelectValue placeholder="Grund wählen …" />
            </SelectTrigger>
            <SelectContent>
              {REASON_CODES.map((code) => (
                <SelectItem key={code} value={code}>
                  {REASON_CODE_LABELS[code]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>

        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Anmerkung (optional)
          <Input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="z. B. Konzerngesellschaft, bewusst zwei Konten"
            className="text-sm"
          />
        </label>
      </div>

      <DialogFooter>
        <Button variant="outline" onClick={onCancel}>
          Abbrechen
        </Button>
        <Button
          variant="destructive"
          disabled={reasonCode == null}
          onClick={() => reasonCode != null && onConfirm(reasonCode, reason)}
        >
          Ablehnen
        </Button>
      </DialogFooter>
    </>
  )
}
