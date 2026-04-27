import {
  Badge,
  Button,
  Card,
  Center,
  Group,
  Loader,
  Paper,
  ScrollArea,
  SegmentedControl,
  Stack,
  Text,
  TextInput,
} from '@mantine/core'
import { IconFilterX, IconSearch } from '@tabler/icons-react'
import { severityColor, statusColor } from './colors'
import type { QueueItem, QueueStatus } from './types'

type QueuePanelProps = {
  query: string
  onQueryChange: (value: string) => void
  statusFilter: 'all' | QueueStatus
  onStatusFilterChange: (value: 'all' | QueueStatus) => void
  queue: QueueItem[]
  selectedId: string
  onSelect: (id: string) => void
  onResetFilters: () => void
  isProcessing: boolean
}

export function QueuePanel({
  query,
  onQueryChange,
  statusFilter,
  onStatusFilterChange,
  queue,
  selectedId,
  onSelect,
  onResetFilters,
  isProcessing,
}: QueuePanelProps) {
  return (
    <Paper withBorder radius="md" p="md">
      <Stack gap="md">
        <Group justify="space-between" align="flex-end" wrap="nowrap">
          <Text fw={600} size="sm">
            Review Queue
          </Text>
          <Button
            variant="subtle"
            size="xs"
            leftSection={<IconFilterX size={14} />}
            onClick={onResetFilters}
          >
            Reset
          </Button>
        </Group>

        <Group grow align="flex-end">
          <TextInput
            label="Search"
            placeholder="Search by sender, subject, or case id"
            leftSection={<IconSearch size={16} />}
            value={query}
            onChange={(event) => onQueryChange(event.currentTarget.value)}
          />
          <div>
            <Text size="sm" fw={500} mb={6}>
              Status
            </Text>
            <SegmentedControl
              fullWidth
              value={statusFilter}
              onChange={(value) => onStatusFilterChange(value as 'all' | QueueStatus)}
              data={[
                { label: 'All', value: 'all' },
                { label: 'Needs Review', value: 'needs review' },
                { label: 'Approved', value: 'approved' },
                { label: 'Rejected', value: 'rejected' },
              ]}
            />
          </div>
        </Group>

        <ScrollArea.Autosize mah={560} type="auto" offsetScrollbars>
          <Stack gap="xs">
            {queue.map((item) => (
              <Card
                key={item.event_id}
                withBorder
                radius="md"
                p="sm"
                style={{
                  cursor: 'pointer',
                  borderColor: item.event_id === selectedId ? 'var(--mantine-color-blue-5)' : undefined,
                }}
                onClick={() => onSelect(item.event_id)}
              >
                <Group justify="space-between" wrap="nowrap" align="flex-start">
                  <div style={{ minWidth: 0 }}>
                    <Group gap={6} mb={4}>
                      <Badge size="xs" variant="filled">
                        {item.event_id}
                      </Badge>
                      <Badge size="xs" color={severityColor(item.ui.severity)} variant="light">
                        {item.ui.severity}
                      </Badge>
                      <Badge size="xs" color={statusColor(item.ui.status)} variant="light">
                        {item.ui.status}
                      </Badge>
                      {item.parsed.duplicate_of && (
                        <Badge size="xs" color="orange" variant="light">
                          duplicate
                        </Badge>
                      )}
                      {item.ui.duplicateCount > 0 && (
                        <Badge size="xs" color="violet" variant="light">
                          +{item.ui.duplicateCount} similar
                        </Badge>
                      )}
                    </Group>
                    <Text fw={600} size="sm" truncate>
                      {item.parsed.headers.subject ?? '(no subject)'}
                    </Text>
                    <Group gap={8} mt={2} wrap="nowrap">
                      <Text c="dimmed" size="xs" truncate>
                        {item.parsed.headers.from_address ?? '(unknown sender)'}
                      </Text>
                      <Text c="dimmed" size="xs">
                        •
                      </Text>
                      <Text c="dimmed" size="xs">
                        {item.parsed.headers.date
                          ? new Date(item.parsed.headers.date).toLocaleString()
                          : 'n/a'}
                      </Text>
                    </Group>
                  </div>
                </Group>
              </Card>
            ))}
            {isProcessing && (
              <Center py="sm">
                <Group gap="xs">
                  <Loader size="sm" />
                  <Text size="sm" c="dimmed">Processing emails…</Text>
                </Group>
              </Center>
            )}
            {queue.length === 0 && !isProcessing && (
              <Paper withBorder radius="md" p="xl">
                <Stack align="center" gap={8}>
                  <Text fw={600}>No matching cases</Text>
                  <Text c="dimmed" size="sm" ta="center">
                    Try clearing filters or adjusting your search terms.
                  </Text>
                  <Button size="xs" variant="light" onClick={onResetFilters}>
                    Clear Filters
                  </Button>
                </Stack>
              </Paper>
            )}
          </Stack>
        </ScrollArea.Autosize>
      </Stack>
    </Paper>
  )
}
