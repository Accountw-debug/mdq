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

/**
 * Zuweisen an eine Person (Spec Sprint 5, Aufgabe 3, Punkt 8).
 *
 * Das Finding-Schema kennt für den Empfänger kein Feld; der Name geht als
 * `assigned_to` in den Entscheidungssatz des UI (Rückmeldung in `ui/NOTES.md`).
 */
export function AssignDialog({
  open,
  onOpenChange,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: (assignedTo: string) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Finding zuweisen</DialogTitle>
          <DialogDescription>
            Das Finding bleibt in Arbeit und erscheint mit dem Namen in der Liste.
          </DialogDescription>
        </DialogHeader>
        {/* Wie beim Ablehnen: eigener Inhalt, damit das Feld beim nächsten Öffnen leer ist. */}
        <AssignForm onCancel={() => onOpenChange(false)} onConfirm={onConfirm} />
      </DialogContent>
    </Dialog>
  )
}

function AssignForm({
  onCancel,
  onConfirm,
}: {
  onCancel: () => void
  onConfirm: (assignedTo: string) => void
}) {
  const [name, setName] = useState('')
  const trimmed = name.trim()

  return (
    <>
      <label className="flex flex-col gap-1 text-xs text-muted-foreground">
        Zuweisen an
        <Input
          value={name}
          autoFocus
          onChange={(event) => setName(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && trimmed !== '') onConfirm(trimmed)
          }}
          placeholder="Name der Kollegin oder des Kollegen"
          className="text-sm"
        />
      </label>

      <DialogFooter>
        <Button variant="outline" onClick={onCancel}>
          Abbrechen
        </Button>
        <Button disabled={trimmed === ''} onClick={() => onConfirm(trimmed)}>
          Zuweisen
        </Button>
      </DialogFooter>
    </>
  )
}
