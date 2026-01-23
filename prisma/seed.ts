import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function main(): Promise<void> {
  console.log('Seeding database...');

  // 営業AI社員の作成
  const salesAI = await prisma.aIEmployee.upsert({
    where: { id: 'ai-employee-sales-001' },
    update: {},
    create: {
      id: 'ai-employee-sales-001',
      name: '営業AI',
      botMention: '@営業AI',
      platform: 'SLACK',
      channelId: 'C0123456789', // 実際のチャンネルIDに置き換える
      difyWorkflowId: 'workflow-sales-leads', // 実際のワークフローIDに置き換える
      difyApiEndpoint: 'https://api.dify.ai/v1/workflows/run',
      isActive: true,
    },
  });

  console.log('Created AI Employee:', salesAI);

  console.log('Seeding completed successfully.');
}

main()
  .catch((e) => {
    console.error('Error during seeding:', e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
