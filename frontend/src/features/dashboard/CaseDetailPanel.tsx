import { useState, useEffect } from 'react'
import { Alert, Badge, Button, Group, Loader, Modal, Paper, ScrollArea, Stack, Text, Title } from '@mantine/core'
import { labelColor } from './colors'
import { ActionSection } from './ActionSection'
import { EvidenceSection } from './EvidenceSection'
import type { DecisionEntry, QueueItem, QueueStatus } from './types'
import { fetchRawEmail } from '@/lib/api'

type CaseDetailPanelProps = {
  selectedItem: QueueItem | null
  note: string
  onNoteChange: (value: string) => void
  onDecision: (status: QueueStatus) => void
  history: DecisionEntry[]
  readOnly?: boolean
}

export function CaseDetailPanel({
  selectedItem,
  note,
  onNoteChange,
  onDecision,
  history,
  readOnly,
}: CaseDetailPanelProps) {
  const [rawOpen, setRawOpen] = useState(false)
  const [rawContent, setRawContent] = useState<string | null>(null)
  const [rawLoading, setRawLoading] = useState(false)
  const [rawError, setRawError] = useState<string | null>(null)

  useEffect(() => { setRawContent(null); setRawError(null) }, [selectedItem?.event_id])

  async function handleViewRaw() {
    setRawOpen(true)
    if (rawContent) return
    setRawLoading(true)
    setRawError(null)
    try {
      const text = await fetchRawEmail(selectedItem!.event_id)
      setRawContent(text)
    } catch {
      setRawError('Failed to load raw email.')
    } finally {
      setRawLoading(false)
    }
  }

  if (!selectedItem) {
    return (
      <Paper withBorder radius="md" p="md" h="100%">
        <Text c="dimmed">Select a case from the queue.</Text>
      </Paper>
    )
  }

  return (
    <>
      <Modal
        opened={rawOpen}
        onClose={() => setRawOpen(false)}
        title="Raw Email"
        size="xl"
      >
        {rawLoading ? (
          <Loader />
        ) : rawError ? (
          <Text c="red">{rawError}</Text>
        ) : (
          <ScrollArea mah={500}>
            <pre style={{ fontSize: '0.75rem', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
              {rawContent}
            </pre>
          </ScrollArea>
        )}
      </Modal>

      <Paper withBorder radius="md" p="md" h="100%">
        <ScrollArea.Autosize mah={640} type="auto" offsetScrollbars>
          <Stack gap="md">
            <Group justify="space-between" align="flex-start">
              <div>
                <Text c="dimmed" size="xs" tt="uppercase">
                  Selected Case
                </Text>
                <Title order={4}>{selectedItem.event_id}</Title>
              </div>
              <Group gap="xs">
                {!readOnly && (
                  <Button size="xs" variant="filled" color="blue" onClick={handleViewRaw}>
                    View Raw
                  </Button>
                )}
                <Badge color={labelColor(selectedItem.parsed.label)}>
                  {selectedItem.parsed.label ?? 'unlabeled'}
                </Badge>
              </Group>
            </Group>

          {selectedItem.parsed.duplicate_of && (
            <Alert color="orange" variant="light" title="Duplicate email">
              This email matches a campaign template already in the queue. Original case:{' '}
              <Text span size="xs" ff="monospace">{selectedItem.parsed.duplicate_of}</Text>
            </Alert>
          )}

          {selectedItem.ui.duplicateCount > 0 && (
            <Alert color="violet" variant="light" title={`${selectedItem.ui.duplicateCount} similar email${selectedItem.ui.duplicateCount > 1 ? 's' : ''} in queue`}>
              Other emails share this campaign template. Look for the{' '}
              <Badge size="xs" color="violet" variant="light">+{selectedItem.ui.duplicateCount} similar</Badge>{' '}
              badge in the queue.
            </Alert>
          )}

          <Paper withBorder radius="md" p="sm">
            <Stack gap={4}>
              <Text fw={600}>{selectedItem.parsed.headers.subject ?? '(no subject)'}</Text>
              <Text size="sm" c="dimmed">
                {selectedItem.parsed.headers.from_address ?? '(unknown sender)'}
              </Text>
              <Group gap={8}>
                <Badge size="sm" variant="light" color="blue">
                  confidence {(selectedItem.ui.confidence * 100).toFixed(0)}%
                </Badge>
                <Badge size="sm" variant="light" color="orange">
                  {selectedItem.ui.severity}
                </Badge>
                <Text size="xs" c="dimmed">
                  {selectedItem.parsed.headers.date
                    ? new Date(selectedItem.parsed.headers.date).toLocaleString()
                    : 'n/a'}
                </Text>
              </Group>
            </Stack>
          </Paper>

          <EvidenceSection item={selectedItem} />

          <ActionSection
            currentStatus={selectedItem.ui.status}
            note={note}
            onNoteChange={onNoteChange}
            onDecision={onDecision}
            history={history}
            readOnly={readOnly}
          />
        </Stack>
        </ScrollArea.Autosize>
      </Paper>
    </>
  )
}
