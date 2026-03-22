import type { Meta, StoryObj } from '@storybook/react'
import NeonButton from './NeonButton'

const meta: Meta<typeof NeonButton> = {
  title: 'UI/NeonButton',
  component: NeonButton,
  parameters: { layout: 'centered' },
}

export default meta

type Story = StoryObj<typeof NeonButton>

export const Primary: Story = {
  args: {
    children: 'Executar scraping',
  },
}
