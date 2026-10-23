<!-- 0724 工单处理 — 详情展示 + 全生命周期处理
     对应原 pages/3_工单处理.py，功能 100% 保留 -->
<template>
  <AppLayout>
    <div class="flex h-[calc(100vh-56px)]">
      <!-- 左侧工单选择器 — 半透明阴影覆盖层 + 独立视觉层
           0819 移动端：有选中工单（URL 带 id）时隐藏列表，仅显详情；桌面 md:flex 恒显 -->
      <div class="w-64 bg-white flex flex-col shrink-0 shadow-[2px_0_12px_rgba(0,0,0,0.08)] z-10 relative"
        :class="route.params.id ? 'hidden md:flex' : ''">
        <div class="p-3 border-b border-gray-100">
          <h3 class="font-semibold text-sm">工单列表</h3>
          <!-- 0820 仅显示我的工单：五角色可用且默认勾选（两层筛选由后端按角色决定；管理员无复选框） -->
          <label v-if="['客服', '客服主管', '办理人', '审批人', '承接人'].includes(role)"
            class="flex items-center gap-1 text-xs text-gray-500 mt-2 cursor-pointer">
            <input v-model="myOrdersOnly" type="checkbox" class="rounded w-3 h-3" @change="loadList" />
            仅显示我的工单
          </label>
          <!-- 0826 侧栏分组：原「审批人分组切换」二选一按钮移除，改为下方列表按「需我处理 / 按需关注」平铺分组 -->
          <input v-model="searchKeyword" @input="onSearch" placeholder="搜索工单（编号/设备/客户/分类/状态）..."
            class="w-full mt-1 px-2 py-1 border border-gray-200 rounded text-xs" />
        </div>
        <div class="flex-1 overflow-y-auto">
          <div v-if="listLoading" class="text-xs text-gray-400 text-center py-8">加载中...</div>
          <div v-else-if="listError" class="text-xs text-red-500 text-center py-8 px-2">{{ listError }}</div>
          <div v-else-if="!filteredOptions.length" class="text-xs text-gray-400 text-center py-8">暂无工单</div>
          <template v-else>
            <div v-for="g in sidebarGroups" :key="g.key">
              <template v-if="g.items.length">
                <!-- 0826 分组标题：实色底条增强分区感 + 可点击折叠（按需组默认收起；搜索时自动展开） -->
                <button type="button" @click="toggleGroup(g.key)"
                  class="w-full px-3 py-1.5 flex items-center justify-between sticky top-0 z-[5] transition"
                  :class="g.key === 'required' ? 'bg-indigo-50 hover:bg-indigo-100' : 'bg-gray-100 hover:bg-gray-200'">
                  <span class="text-xs font-semibold flex items-center gap-1"
                    :class="g.key === 'required' ? 'text-primary' : 'text-gray-500'">
                    <ChevronDown :size="12" class="transition-transform shrink-0"
                      :class="isGroupCollapsed(g.key) ? '-rotate-90' : ''" />
                    {{ g.title }}
                  </span>
                  <span class="text-[10px]" :class="g.key === 'required' ? 'text-primary/50' : 'text-gray-400'">{{ g.items.length }}</span>
                </button>
                <p v-if="g.hint && !isGroupCollapsed(g.key)" class="px-3 py-1 text-[10px] text-gray-400 leading-tight">{{ g.hint }}</p>
                <button v-for="opt in g.items" v-show="!isGroupCollapsed(g.key)" :key="opt.id"
                  @click="selectComplaint(opt.id)"
                  :class="['w-full text-left px-3 py-2 text-sm border-b border-gray-50 transition',
                    activeId === opt.id ? 'bg-primary/10 text-primary' : 'hover:bg-gray-50']">
                  <div class="truncate">{{ opt.complaint_no }}</div>
                  <div class="text-xs text-gray-400 truncate">{{ opt.customer_name }} · {{ opt.status }}</div>
                </button>
              </template>
            </div>
          </template>
        </div>
      </div>

      <!-- 右侧详情区 — 0819 移动端无选中工单（URL 无 id）时隐藏，仅显列表 -->
      <div class="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6"
        :class="route.params.id ? '' : 'hidden md:block'">
        <!-- 0819 移动端返回列表按钮（桌面 md:hidden 不显示） -->
        <button class="md:hidden inline-flex items-center gap-1.5 text-sm font-medium text-primary py-1"
          @click="router.push('/work-order')">
          <ArrowLeft :size="16" /> 返回工单列表
        </button>
        <div v-if="!complaint" class="text-center text-gray-400 py-16">请从左侧选择工单</div>

        <template v-else>
          <!-- 0730 头部信息卡片 — 0820 重构：去 emoji，「字段：内容 |」分组分行 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4 space-y-3">
            <!-- 行 1：工单号 + 状态徽章 -->
            <div class="flex items-center justify-between flex-wrap gap-3">
              <h2 class="text-lg font-bold">{{ complaint.complaint_no }}</h2>
              <div class="flex items-center gap-2">
                <StatusBadge :status="complaint.status" />
                <PriorityBadge :priority="complaint.priority" />
              </div>
            </div>

            <!-- 行 2：客户与设备 -->
            <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-gray-600">
              <span>客户：<span class="text-gray-800 font-medium">{{ complaint.customer_name || '—' }}</span></span>
              <span class="text-gray-200">|</span>
              <span>设备型号：<span class="text-gray-800 font-medium">{{ complaint.equipment_model || '—' }}</span></span>
              <span class="text-gray-200">|</span>
              <!-- 1015 设备编号口径按客诉场景：工艺调试类→厂内编号，其余→出厂编号 -->
              <span>{{ equipmentSnLabel(complaint.scene_category) }}：<span class="text-gray-800 font-medium">{{ complaint.equipment_sn || '—' }}</span></span>
              <span class="text-gray-200">|</span>
              <span>部位：<span class="text-gray-800 font-medium">{{ complaint.device_part || '—' }}</span></span>
              <span class="text-gray-200">|</span>
              <span>软件版本：<span class="text-gray-800 font-medium">{{ complaint.software_version || '—' }}</span></span>
            </div>

            <!-- 行 3：分类与影响 -->
            <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-gray-600">
              <span>故障分类：<span class="text-gray-800 font-medium">{{ complaint.fault_category || '—' }}</span></span>
              <span class="text-gray-200">|</span>
              <span>客诉场景分类：<span class="text-gray-800 font-medium">{{ complaint.scene_category || '—' }}</span></span>
              <span class="text-gray-200">|</span>
              <span>影响：<span class="text-gray-800 font-medium">{{ complaint.impact_level || '未标注' }}</span></span>
            </div>

            <!-- 行 4：录入人 / 客诉发生时间 / 创建时间（1019 拆分）/ 客户期望 / 进度 -->
            <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500">
              <span>录入人：<span class="text-gray-700 font-medium">{{ complaint.created_by || '—' }}</span></span>
              <span class="text-gray-200">|</span>
              <!-- 1019 客诉发生时间（工单号日期段取此值） -->
              <span>客诉发生时间：<span class="text-gray-700 font-medium">{{ (complaint.occurred_at || '').slice(0, 10) || '—' }}</span></span>
              <span class="text-gray-200">|</span>
              <!-- 1019 创建时间 = 真实录入系统时刻（不再被导入的表内日期覆盖） -->
              <span>创建时间：<span class="text-gray-700 font-medium">{{ complaint.created_at || '—' }}</span></span>
              <span class="text-gray-200">|</span>
              <span>客户期望：<span :class="['font-medium', complaint.expected_complete_date && new Date(complaint.expected_complete_date) < new Date() ? 'text-red-600' : 'text-gray-700']">{{ complaint.expected_complete_date || '—' }}</span></span>
              <span class="text-gray-200">|</span>
              <!-- 进度条 — inline -->
              <span class="inline-flex items-center gap-1.5">
                <span>{{ progressInfo.method === 'actual' ? '承接人处理进度' : '工单跟进进度' }}：</span>
                <span class="inline-block w-14 bg-gray-100 rounded-full h-1.5 align-middle">
                  <span class="block bg-primary h-1.5 rounded-full transition-all duration-500" :style="{ width: (progressInfo.pct || 0) + '%' }"></span>
                </span>
                <span class="text-gray-700 font-medium">{{ progressInfo.pct || 0 }}%</span>
              </span>
            </div>
            <!-- 行 5：办理人 / 指派 / 预估工时 / 排期 / 处理耗时 -->
            <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500">
              <span>办理人：<span class="text-gray-700 font-medium">{{ complaint.handler_name || '—' }}</span></span>
              <span class="text-gray-200">|</span>
              <!-- 0819 指派行：审批人 + 承接人/参与人 -->
              <span>指派：<span class="text-gray-700 font-medium">{{ assigneeSummary || '—' }}</span></span>
              <span class="text-gray-200">|</span>
              <span>预估工时：<span class="text-gray-700 font-medium">{{ complaint.estimated_hours ? complaint.estimated_hours + 'h' : '—' }}</span></span>
              <span class="text-gray-200">|</span>
              <span>排期时间：<span class="text-gray-700 font-medium">{{ formatDateTime(complaint.planned_start_time) || '—' }} → {{ formatDateTime(complaint.planned_end_time) || '—' }}</span></span>
              <span class="text-gray-200">|</span>
              <span>处理耗时：<span class="text-gray-700 font-medium">{{ (processingHours && (complaint.status === '待客服处理' || complaint.status === '已关闭')) ? processingHours : '—' }}</span></span>
            </div>
          </div>

          <!-- 0820 详情信息：关联工单置顶 + 故障现象（原两张卡片合并，去 emoji） -->
          <div class="bg-white rounded-lg border border-gray-200 p-4 space-y-3">
            <!-- 0807 返修 + 关联工单信息（原独立卡片，0820 合并并置于故障现象上方） -->
            <div>
              <h4 class="text-sm text-gray-700">关联工单</h4>
              <div class="mt-1 flex flex-wrap gap-x-6 gap-y-1 text-sm">
                <div>
                  返修：<strong :class="complaint.is_rework ? 'text-amber-700' : 'text-gray-500'">
                    {{ complaint.is_rework ? '是（返修工单）' : '否' }}
                  </strong>
                </div>
                <div v-if="linkedComplaints.length">
                  关联工单：
                  <span v-for="(lc, i) in linkedComplaints.slice(0, LINKED_INLINE_LIMIT)" :key="lc.id">
                    <router-link :to="`/work-order/${lc.id}`"
                      class="text-primary hover:underline font-medium">{{ lc.no }}</router-link>
                    <span v-if="i < Math.min(linkedComplaints.length, LINKED_INLINE_LIMIT) - 1">, </span>
                  </span>
                  <!-- 0915 关联工单较多时折叠，弹窗表格查看全部 -->
                  <button v-if="linkedComplaints.length > LINKED_INLINE_LIMIT" type="button"
                    class="ml-1 text-primary hover:underline font-medium"
                    @click="openLinkedModal">…共 {{ linkedComplaints.length }} 个，展开查看</button>
                </div>
                <div v-else class="text-gray-400">
                  暂无关联工单
                </div>
              </div>
            </div>
            <div>
              <h4 class="text-sm text-gray-700">故障现象</h4>
              <div class="mt-1 p-3 bg-blue-50 rounded text-sm">{{ complaint.fault_phenomenon }}</div>
            </div>
            <div v-if="complaint.reproduction_steps">
              <h4 class="text-sm text-gray-700">排查记录</h4>
              <pre class="mt-1 p-3 bg-gray-50 rounded text-sm whitespace-pre-wrap font-sans">{{ complaint.reproduction_steps }}</pre>
            </div>
            <div v-if="complaint.root_cause">
              <h4 class="text-sm text-gray-700">根因分析</h4>
              <div class="mt-1 p-3 bg-green-50 rounded text-sm">{{ complaint.root_cause }}</div>
            </div>
            <div v-if="complaint.solution">
              <h4 class="text-sm text-gray-700">解决方案</h4>
              <div class="mt-1 p-3 bg-green-50 rounded text-sm">{{ complaint.solution }}</div>
            </div>
            <div v-if="complaint.resolution_note">
              <h4 class="text-sm text-gray-700">处理备注</h4>
              <pre class="mt-1 p-3 bg-gray-50 rounded text-sm whitespace-pre-wrap font-sans">{{ complaint.resolution_note }}</pre>
            </div>
            <div v-if="complaint.customer_confirmed" class="flex gap-6">
              <div>客户确认：<strong>已确认</strong></div>
              <div>满意度：<strong>{{ '⭐'.repeat(complaint.satisfaction || 0) || '-' }}</strong></div>
            </div>
          </div>

          <!-- 0915 关联工单弹窗：表格展示全部关联工单，点击行跳转对应详情 -->
          <Teleport to="body">
            <div v-if="showLinkedModal" class="fixed inset-0 z-50 flex items-center justify-center">
              <div class="absolute inset-0 bg-black/40" @click="showLinkedModal = false"></div>
              <div class="relative bg-white rounded-lg shadow-xl w-full max-w-6xl mx-4 max-h-[80vh] flex flex-col">
                <div class="flex items-center justify-between px-5 py-4 border-b border-gray-200 shrink-0">
                  <h3 class="text-base font-medium">关联工单（{{ linkedComplaints.length }}）</h3>
                  <button type="button" class="text-gray-400 hover:text-gray-600" @click="showLinkedModal = false">
                    <X :size="18" />
                  </button>
                </div>
                <div class="overflow-auto flex-1">
                  <table class="w-full text-sm">
                    <thead class="sticky top-0">
                      <tr class="bg-gray-50 border-b border-gray-200 text-left text-xs text-gray-500">
                        <th class="px-3 py-3">工单编号</th>
                        <th class="px-3 py-3">设备编号</th>
                        <th class="px-3 py-3">优先级</th>
                        <th class="px-3 py-3">状态</th>
                        <th class="px-3 py-3">问题</th>
                        <th class="px-3 py-3">解决方案</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-if="linkedLoading">
                        <td colspan="6" class="px-4 py-8 text-center text-gray-400">加载中…</td>
                      </tr>
                      <tr v-else-if="linkedError">
                        <td colspan="6" class="px-4 py-8 text-center text-gray-400">
                          {{ linkedError }}
                          <button type="button" class="ml-2 text-primary hover:underline" @click="openLinkedModal">重试</button>
                        </td>
                      </tr>
                      <template v-else>
                        <!-- 0915 仅工单编号可点击跳转，整行不带点击 -->
                        <tr v-for="row in linkedRows" :key="row.id"
                          class="border-b border-gray-100 hover:bg-gray-50/50 transition">
                          <td class="px-3 py-2">
                            <a href="#" @click.prevent="goLinkedDetail(row.id)"
                              class="text-primary hover:underline font-medium mono text-xs">{{ row.complaint_no }}</a>
                          </td>
                          <td class="px-3 py-2 mono text-xs">{{ row.equipment_sn || '—' }}</td>
                          <td class="px-3 py-2"><PriorityBadge :priority="row.priority" /></td>
                          <td class="px-3 py-2"><StatusBadge :status="row.status" /></td>
                          <td class="px-3 py-2">
                            <span class="block max-w-[16rem] truncate" :title="row.fault_phenomenon">{{ row.fault_phenomenon || '—' }}</span>
                          </td>
                          <td class="px-3 py-2">
                            <span class="block max-w-[16rem] truncate" :title="row.solution">{{ row.solution || '—' }}</span>
                          </td>
                        </tr>
                        <!-- 关联中已被删除的工单：按存储编号展示，不可点击 -->
                        <tr v-for="del in linkedDeleted" :key="'del-' + del.id" class="border-b border-gray-100 text-gray-400">
                          <td class="px-3 py-2 mono text-xs">{{ del.no }}</td>
                          <td colspan="5" class="px-3 py-2">已删除</td>
                        </tr>
                        <tr v-if="!linkedRows.length && !linkedDeleted.length">
                          <td colspan="6" class="px-4 py-8 text-center text-gray-400">暂无关联工单</td>
                        </tr>
                      </template>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </Teleport>

          <!-- 0803 统一工单日志（取代旧备注+客户备注+进度历史三个独立区块） -->
          <WorkOrderTimeline
            :logs="timelineLogs"
            :legacyRemarks="complaint.remarks"
            :legacyCustomerNote="complaint.customer_note"
            :legacyCustomerSelfCheck="complaint.customer_self_check"
          />

          <!-- 附件展示：图片可点击放大，文档可下载 -->
          <div v-if="attachments.length" class="bg-white rounded-lg border border-gray-200 p-4">
            <h4 class="text-sm text-gray-700 mb-3">附件（{{ attachments.length }}）</h4>
            <div v-if="attachmentMsg" class="text-xs text-red-500 mb-2">{{ attachmentMsg }}</div>
            <!-- 图片（缩略图 + 点击放大） -->
            <div v-if="imgAtts.length" class="grid grid-cols-2 gap-2 mb-3 sm:grid-cols-4">
              <div v-for="att in imgAtts" :key="att.id"
                class="relative group cursor-pointer rounded overflow-hidden border border-gray-200 hover:ring-2 hover:ring-primary/30 transition"
                @click="previewImage = att">
                <img :src="`/api/files/${att.id}/download${tokenParam}`" :alt="att.filename"
                  class="w-full h-24 object-cover" />
                <div class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/50 to-transparent p-1">
                  <span class="text-[10px] text-white truncate block">{{ att.filename }}</span>
                </div>
                <span class="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition text-xs bg-white/80 rounded px-1">
                  放大
                </span>
                <!-- 0826 图片附件删除（权限内 hover 可见） -->
                <button v-if="canManageFiles" type="button" @click.stop="attachmentDeleteTarget = att" title="删除附件"
                  class="absolute top-1 left-1 opacity-0 group-hover:opacity-100 transition w-6 h-6 flex items-center justify-center text-xs bg-white/90 text-red-600 rounded hover:bg-red-50">
                  🗑
                </button>
              </div>
            </div>
            <!-- 图片放大遮罩 -->
            <Teleport to="body">
              <div v-if="previewImage" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/80 cursor-pointer"
                @click="previewImage = null">
                <img :src="`/api/files/${previewImage.id}/download${tokenParam}`" :alt="previewImage.filename"
                  class="max-w-[90vw] max-h-[90vh] object-contain rounded shadow-2xl" />
                <button @click="previewImage = null"
                  class="absolute top-4 right-4 w-10 h-10 rounded-full bg-white/20 hover:bg-white/40 text-white text-xl transition">
                  ✕
                </button>
                <a :href="`/api/files/${previewImage.id}/download${tokenParam}`" @click.stop
                  class="absolute bottom-4 right-4 px-4 py-2 bg-white/90 text-gray-800 rounded text-sm hover:bg-white transition">
                  📥 下载原图
                </a>
              </div>
            </Teleport>
            <!-- 文档（下载链接） -->
            <div v-if="docAtts.length" class="space-y-1">
              <div v-for="att in docAtts" :key="att.id"
                class="flex items-center gap-2 text-sm py-1.5 px-2 rounded hover:bg-gray-50 group">
                <span class="flex-1 text-gray-700 truncate">{{ att.filename }}</span>
                <span class="text-xs text-gray-400 shrink-0">({{ (att.file_size / 1024).toFixed(1) }}KB)</span>
                <a :href="`/api/files/${att.id}/download${tokenParam}`"
                  class="shrink-0 px-3 py-1 bg-primary text-white text-xs rounded hover:bg-primary/90 transition">
                  📥 下载
                </a>
                <!-- 0826 文档附件删除（权限内可见） -->
                <button v-if="canManageFiles" type="button" @click="attachmentDeleteTarget = att" title="删除附件"
                  class="shrink-0 px-2 py-1 border border-red-200 text-red-600 text-xs rounded hover:bg-red-50 transition">
                  🗑 删除
                </button>
              </div>
            </div>
          </div>

          <!-- 0728 AI 智能辅助面板（v2.1 3_工单处理.py 330-388 行）
               0821 「指派承接人」状态下可折叠、默认折叠；其他状态恒展开、无折叠控件 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <h4 class="text-sm font-semibold">
              <button v-if="isAssigneeAssignmentStatus" type="button"
                @click="aiPanelCollapsed = !aiPanelCollapsed"
                class="w-full flex items-center gap-2 text-left cursor-pointer">
                <span>AI 智能辅助</span>
                <!-- 0821 折叠提示：带边框的按钮样式，提示点击展开/收起（整行均可点击） -->
                <span class="shrink-0 inline-flex items-center gap-1 px-2 py-1 rounded border border-gray-300 text-xs font-normal text-gray-600 bg-gray-50 hover:bg-gray-100 transition">
                  {{ aiPanelCollapsed ? '点击展开' : '点击收起' }}
                  <ChevronDown :size="14" class="text-gray-400 transition-transform duration-200"
                    :class="aiPanelCollapsed ? '' : 'rotate-180'" />
                </span>
              </button>
              <span v-else>AI 智能辅助</span>
            </h4>
            <div v-if="!aiPanelCollapsed" class="mt-4 space-y-4">
              <!-- 0729 AI 免责提示 -->
              <p class="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 flex items-start gap-1.5">
                <span><strong>AI 建议仅供参考</strong> — 所有 AI 生成内容（相似案例、排查清单、解决方案）均为辅助参考，实际决策请结合专业判断与实际情况。</span>
              </p>
              <!-- 左：相似历史案例（FTS5 秒出，自动检索） -->
              <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div>
                  <h5 class="text-xs text-gray-700 mb-2">相似历史案例</h5>
                  <div v-if="similarLoading" class="text-xs text-gray-400 text-center py-4">检索中...</div>
                  <div v-else-if="!similarCases.length" class="text-xs text-gray-400 py-2">未找到高度相似案例</div>
                  <div v-else class="space-y-2 max-h-72 overflow-y-auto">
                      <CaseCard v-for="(c, i) in similarCases" :key="i" :entry="c" :complaint-no="complaint?.complaint_no" source-type="fts5_auto" :case-feedback-map="caseFeedbackMap" />
                  </div>
                </div>
                <!-- 右：推荐排查清单 -->
                <div>
                  <h5 class="text-xs text-gray-700 mb-2">推荐排查 Checklist</h5>
                  <div v-if="checklistLoading" class="text-xs text-gray-400 py-4 text-center">加载中...</div>
                  <div v-else-if="!checklistItems.length" class="text-xs text-gray-400 py-2">暂无</div>
                  <div v-else class="space-y-1 max-h-60 overflow-y-auto">
                    <label v-for="(item, i) in checklistItems" :key="i" class="flex items-start gap-1.5 text-xs cursor-pointer hover:text-gray-900">
                      <input type="checkbox" v-model="checklistChecked[i]" class="mt-0.5 rounded shrink-0" />
                      <span class="text-gray-600">{{ item }}</span>
                    </label>
                  </div>
                </div>
              </div>
              <!-- AI 方案推荐（手动触发，LLM 重排） -->
              <div class="border-t border-gray-100 pt-3">
                <button @click="doAiSolution" :disabled="aiSolutionLoading"
                  class="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold
                         bg-primary text-white hover:bg-primary/90
                         disabled:opacity-50 disabled:cursor-not-allowed
                         shadow-sm hover:shadow-md transition-all duration-200"
                  title="从知识库检索相似案例，结合 AI 知识给出解决方案">
                  <span class="text-base">📚</span>
                  <span>{{ aiSolutionLoading ? '🔍 正在检索历史案例并生成方案建议...' : 'AI 智能推荐解决方案' }}</span>
                  <span v-if="!aiSolutionLoading" class="text-white/60 text-xs">→ 从知识库检索相似案例，结合 AI 知识给出方案</span>
                </button>
                <div v-if="aiSolutionResult" class="mt-4 border border-gray-200 rounded-lg p-4 bg-white">
                  <h5 class="text-sm font-semibold mb-2">案例搜索方案结果</h5>
                  <div class="text-sm text-gray-700 prose prose-sm max-w-none whitespace-pre-wrap">{{ aiSolutionResult.summary }}</div>
                  <div v-if="aiSolutionResult.source_cases?.length" class="mt-3 space-y-2">
                    <div class="text-xs text-gray-500">下方每个参考案例可点击查看详情：</div>
                    <CaseCard v-for="(c, i) in aiSolutionResult.source_cases" :key="i" :entry="c" :complaint-no="complaint?.complaint_no" source-type="ai_solution" :case-feedback-map="caseFeedbackMap" />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 操作区 — 根据状态显示不同组件 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4 sm:p-6">
            <h3 class="text-lg font-semibold mb-4">操作区</h3>

            <!-- 0731 评价卡片显示期间冻结操作区，避免用户在评价前看到下一状态的操作 -->
            <template v-if="!awaitingFeedback">

            <!-- ═══════════ 1016 工单预警（客服/客服主管；已关闭/已撤回不显示）═══════════ -->
            <div v-if="canRaiseWarning" class="mb-4 p-3 rounded border border-amber-200 bg-amber-50/70 space-y-2">
              <div class="flex items-center justify-between flex-wrap gap-2">
                <div class="text-xs text-amber-800">
                  出现临期、客户催办或退机风险等情况时，可发起预警通知客服主管与承办人（高风险会额外知会指定人员）。
                </div>
                <button @click="openWarning"
                  class="px-4 py-1.5 border border-amber-300 bg-white text-amber-800 rounded-base text-sm font-medium hover:bg-amber-100 transition shrink-0">
                  ⚠️ 预警处理
                </button>
              </div>
              <div v-if="warningMsg" :class="['text-xs', warningOk ? 'text-emerald-700' : 'text-red-600']">{{ warningMsg }}</div>
            </div>

            <!-- ═══════════ 1020 退回审批（审批期间状态不变）═══════════ -->
            <div v-if="returnRequestPending" class="mb-4 p-4 rounded border border-indigo-200 bg-indigo-50 space-y-2">
              <div class="text-sm font-semibold text-indigo-800">🔁 退回申请待审批 · {{ returnTypeLabel }}</div>
              <div class="text-xs text-indigo-700">
                申请人：{{ complaint.return_request_by || '—' }}　|　原因：{{ complaint.return_request_reason || '—' }}
              </div>
              <template v-if="canReviewReturn">
                <textarea v-model="returnReviewNote" rows="2" placeholder="审批意见（选填）"
                  class="w-full px-3 py-2 border border-indigo-200 rounded text-sm"></textarea>
                <div class="flex flex-wrap gap-2">
                  <button @click="doReviewReturn('approved')" :disabled="returnReviewing"
                    class="px-4 py-2 bg-emerald-600 text-white rounded text-sm hover:bg-emerald-700 disabled:opacity-50 transition">
                    ✅ {{ returnReviewing ? '处理中...' : '同意退回' }}
                  </button>
                  <button @click="doReviewReturn('rejected')" :disabled="returnReviewing"
                    class="px-4 py-2 bg-red-600 text-white rounded text-sm hover:bg-red-700 disabled:opacity-50 transition">
                    ❌ 驳回
                  </button>
                </div>
                <div v-if="returnReviewMsg" :class="['text-xs', returnReviewOk ? 'text-green-600' : 'text-red-500']">{{ returnReviewMsg }}</div>
              </template>
              <div v-else class="text-xs text-indigo-600">等待{{ returnReviewerLabel }}审批；审批期间工单状态保持不变。</div>
            </div>

            <!-- ═══════════ 0819 v3.0 新状态机操作区 ═══════════ -->

            <!-- 客服主管审核（客诉审核）→ 客服主管/管理员 -->
            <div v-if="complaint.status === '客服主管审核' && complaint.sub_type === 'intake'" class="space-y-3">
              <div v-if="role === '客服主管' || role === '管理员'" class="space-y-3">
                <div class="p-3 bg-blue-50 text-blue-800 rounded text-sm">
                  客诉审核：通过需确认优先级与去向；拒绝退回客服修改（重提后重新审核）。优先级与去向仅在通过时生效。
                </div>
                <div v-if="complaint.supervisor_rejection_note && complaint.re_edited"
                  class="p-3 bg-amber-50 text-amber-800 rounded text-sm">客服已重新编辑 — 请重新审核</div>
                <div>
                  <label class="text-xs text-gray-500 block mb-1">优先级（仅通过时生效） <span class="text-red-400">*</span></label>
                  <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    <button v-for="p in ['P0', 'P1', 'P2', 'P3']" :key="p" @click="intakeForm.priority = p"
                      :class="['py-2 rounded font-semibold text-white text-sm transition',
                        intakeForm.priority === p ? 'ring-2 ring-offset-1 ring-gray-600' : 'opacity-80 hover:opacity-100',
                        p === 'P0' ? 'bg-red-600' : p === 'P1' ? 'bg-amber-500' : p === 'P2' ? 'bg-emerald-500' : 'bg-blue-500']">
                      {{ p }} 级
                    </button>
                  </div>
                </div>
                <div>
                  <label class="text-xs text-gray-500 block mb-1">通过后去向（仅通过时生效） <span class="text-red-400">*</span></label>
                  <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <button @click="intakeForm.route = '待客户排查'"
                      :class="['px-4 py-2 rounded text-sm font-medium transition',
                        intakeForm.route === '待客户排查' ? 'bg-primary text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200']">
                      🔍 转待客户排查
                    </button>
                    <button @click="intakeForm.route = '指派审批人'"
                      :class="['px-4 py-2 rounded text-sm font-medium transition',
                        intakeForm.route === '指派审批人' ? 'bg-primary text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200']">
                      📌 转办理人处理
                    </button>
                  </div>
                </div>
                <!-- 0820 审核评估 + AI 推荐客户自排查（复用客诉录入的 AI 自排查链路）
                     0826 统一单一评估框：通过/拒绝/撤回共用，不再弹出独立的拒绝/撤回输入面板 -->
                <div class="space-y-2">
                  <button type="button" @click="doIntakeSelfCheck"
                    :disabled="intakeSelfCheckLoading || !complaint.fault_phenomenon?.trim()"
                    class="w-full py-2.5 text-sm bg-gray-100 text-gray-700 hover:bg-gray-200 rounded-base disabled:opacity-50 transition font-normal">
                    {{ intakeSelfCheckLoading ? '⏳ AI 分析中...' : '🔍 AI 推荐客户自排查（生成客户可自行排查的建议）' }}
                  </button>
                  <p class="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 flex items-start gap-1.5">
                    <span><strong>AI 建议仅供参考</strong> — 排查建议面向产线操作工，为通用性安全排查步骤，具体故障排查请以工程师诊断为准。</span>
                  </p>
                  <div>
                    <label class="text-xs text-gray-500 block mb-1">审核评估 <span class="text-red-400">*</span></label>
                    <textarea v-model="intakeForm.evaluation" rows="5" placeholder="审核评估内容（必填，通过 / 拒绝 / 撤回共用，可点击上方 AI 生成）..."
                      class="w-full px-3 py-2 border border-gray-300 rounded text-sm"></textarea>
                  </div>
                  <div v-if="intakeSelfCheckSuccess" class="flex items-center gap-2 text-green-600 text-sm bg-green-50 border border-green-200 rounded px-3 py-2">
                    <span>AI 建议已填入上方「审核评估」栏</span>
                  </div>
                </div>
                <!-- 0826 三个动作直接提交：拒绝/撤回复用当前评估内容，经确认弹窗防误触 -->
                <div class="flex flex-wrap gap-3">
                  <button @click="doIntakeApprove" :disabled="intakeSubmitting"
                    class="px-5 py-2 bg-emerald-600 text-white rounded font-medium text-sm hover:bg-emerald-700 disabled:opacity-50 transition">
                    ✅ {{ intakeSubmitting ? '处理中...' : '审核通过' }}
                  </button>
                  <button @click="askIntakeReject" :disabled="!intakeForm.evaluation.trim() || intakeSubmitting"
                    class="px-5 py-2 border-2 border-red-400 text-red-600 rounded font-medium text-sm hover:bg-red-50 disabled:opacity-50 transition">
                    ❌ 拒绝审核
                  </button>
                  <!-- 0826 撤回操作移交录入客服，在看板发起（全流程除已关闭） -->
                </div>
                <div v-if="intakeMsg" :class="['text-sm', intakeOk ? 'text-emerald-600' : 'text-red-500']">{{ intakeMsg }}</div>
              </div>
              <div v-else class="p-4 bg-amber-50 text-amber-800 rounded text-sm">等待客服主管审核客诉内容…</div>
            </div>

            <!-- 客服主管审核（邮件审核）→ 客服主管/管理员 -->
            <div v-else-if="complaint.status === '客服主管审核' && complaint.sub_type === 'email'" class="space-y-3">
              <div v-if="role === '客服主管' || role === '管理员'" class="space-y-3">
                <div class="p-3 bg-violet-50 text-violet-800 rounded text-sm">
                  该工单的客户邮件正在等待主管审核
                </div>
                <div v-if="emailDraft" class="bg-white border border-gray-200 rounded p-3 space-y-2">
                  <div>
                    <span class="text-xs text-gray-400">主题：</span>
                    <span class="text-sm text-gray-800">{{ emailDraft.subject || '（无主题）' }}</span>
                  </div>
                  <div>
                    <span class="text-xs text-gray-400">正文：</span>
                    <div class="text-sm text-gray-700 mt-1 whitespace-pre-wrap">{{ emailDraft.body || '（无正文）' }}</div>
                  </div>
                </div>
                <div class="flex gap-3">
                  <button @click="doEmailApprove" :disabled="emailReviewLoading"
                    class="px-5 py-2 bg-emerald-600 text-white rounded font-medium text-sm hover:bg-emerald-700 disabled:opacity-50 transition">
                    ✅ {{ emailReviewLoading ? '处理中...' : '批准发送' }}
                  </button>
                  <button @click="emailRejectMode = true" :disabled="emailReviewLoading"
                    class="px-5 py-2 border-2 border-red-400 text-red-600 rounded font-medium text-sm hover:bg-red-50 transition">
                    ❌ 拒绝
                  </button>
                </div>
                <div v-if="emailRejectMode" class="space-y-3">
                  <textarea v-model="emailRejectNote" rows="3" placeholder="请填写拒绝原因（可选）..."
                    class="w-full px-3 py-2 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-red-300"></textarea>
                  <div class="flex gap-3">
                    <button @click="doEmailReject" :disabled="emailReviewLoading"
                      class="px-5 py-2 bg-red-600 text-white rounded font-medium text-sm hover:bg-red-700 disabled:opacity-50 transition">
                      {{ emailReviewLoading ? '提交中...' : '确认拒绝' }}
                    </button>
                    <button @click="emailRejectMode = false; emailRejectNote = ''"
                      class="px-4 py-2 border border-gray-300 rounded text-sm hover:bg-gray-50 transition">取消</button>
                  </div>
                </div>
                <div v-if="emailReviewMsg" :class="['text-sm', emailReviewOk ? 'text-emerald-600' : 'text-red-500']">{{ emailReviewMsg }}</div>
              </div>
              <div v-else class="p-4 bg-violet-50 text-violet-800 rounded text-sm">等待客服主管审核邮件…</div>
            </div>

            <!-- 待客服处理（待修改）→ 客服编辑重提 -->
            <div v-else-if="complaint.status === '待客服处理' && complaint.sub_type === 'rework'" class="space-y-3">
              <div v-if="(role === '客服' && isCreator) || role === '管理员'" class="space-y-3">
                <div v-if="complaint.email_review_status === 'rejected'"
                  class="p-3 bg-red-50 text-red-700 rounded text-sm">
                  邮件审核被拒：{{ complaint.email_review_note || '（无原因）' }} — 请修改邮件内容后重新提交
                </div>
                <div v-else-if="complaint.supervisor_rejection_note"
                  class="p-3 bg-red-50 text-red-700 rounded text-sm">
                  {{ returnNote?.reasonLabel }}：{{ returnNote?.reason }}
                </div>
                <div class="flex flex-wrap gap-3">
                  <button @click="store.openEdit(complaint.id)"
                    class="px-5 py-2 border border-gray-300 rounded text-sm hover:bg-gray-50 transition">
                    ✏️ 编辑工单
                  </button>
                  <button @click="doResubmit" :disabled="resubmitLoading"
                    class="px-5 py-2 bg-primary text-white rounded text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition">
                    📤 {{ resubmitLoading ? '提交中...' : '重新提交审核' }}
                  </button>
                </div>
                <div v-if="resubmitMsg" :class="['text-sm', resubmitOk ? 'text-emerald-600' : 'text-red-500']">{{ resubmitMsg }}</div>
              </div>
              <div v-else class="p-4 bg-amber-50 text-amber-800 rounded text-sm">{{ role === '客服' ? '该工单由其他客服录入，仅录入客服可操作' : '客服修改中…' }}</div>
            </div>

            <!-- 待客服处理（待客户确认）→ 客服确认关闭/邮件 -->
            <div v-else-if="complaint.status === '待客服处理' && complaint.sub_type === 'customer_confirm'">
              <CustomerConfirmForm v-if="(role === '客服' && isCreator) || role === '管理员'"
                :complaintId="complaint.id"
                :customerEmail="complaint.customer_email"
                :complaintNo="complaint.complaint_no"
                :remarks="complaint.remarks"
                :emailReviewStatus="complaint.email_review_status"
                :emailReviewNote="complaint.email_review_note"
                :emailDraftContent="complaint.email_draft_content"
                :canConfirm="true"
                @done="onActionDone('confirm')"
                @refresh="reload" />
              <div v-else class="p-4 bg-teal-50 text-teal-800 rounded text-sm">{{ role === '客服' ? '该工单由其他客服录入，仅录入客服可操作' : '等待客服联系客户确认…' }}</div>
            </div>

            <!-- 待客户排查 → 客服提交排查结果 -->
            <div v-else-if="complaint.status === '待客户排查'" class="space-y-3">
              <div v-if="(role === '客服' && isCreator) || role === '管理员'" class="space-y-3">
                <div class="p-3 bg-purple-50 text-purple-800 rounded text-sm">
                  待客户排查：记录排查备注，提交「已解决」将直接转入待客户确认；「未解决」转入指派审批人。
                </div>
                <textarea v-model="investigationRemark" rows="4" placeholder="排查备注（如客户反馈、排查发现）…"
                  class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm focus:ring-2 focus:ring-primary/30"></textarea>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <button @click="doInvestigation('resolved')" :disabled="!!investigationSubmitting"
                    class="px-4 py-2 bg-emerald-600 text-white rounded text-sm font-medium hover:bg-emerald-700 disabled:opacity-50 transition">
                    ✅ {{ investigationSubmitting === 'resolved' ? '提交中...' : '已解决 → 待客户确认' }}
                  </button>
                  <button @click="doInvestigation('unresolved')" :disabled="!!investigationSubmitting"
                    class="px-4 py-2 bg-orange-600 text-white rounded text-sm font-medium hover:bg-orange-700 disabled:opacity-50 transition">
                    ⚠️ {{ investigationSubmitting === 'unresolved' ? '提交中...' : '未解决 → 指派审批人' }}
                  </button>
                </div>
                <div v-if="investigationMsg" :class="['text-xs', investigationOk ? 'text-green-600' : 'text-red-500']">{{ investigationMsg }}</div>
              </div>
              <div v-else class="p-4 bg-purple-50 text-purple-800 rounded text-sm">{{ role === '客服' ? '该工单由其他客服录入，仅录入客服可操作' : '待客户排查（仅客服/管理员可提交排查结果）' }}</div>
            </div>

            <!-- 指派审批人 → 办理人指派 -->
            <div v-else-if="complaint.status === '指派审批人'" class="space-y-3">
              <div v-if="role === '办理人' || role === '管理员'" class="space-y-3">
                <div class="p-3 bg-amber-50 text-amber-800 rounded text-sm">指派审批人（候选：办理人/审批人）</div>
                <div>
                  <label class="text-xs text-gray-500 block mb-1">审批人（单选） <span class="text-red-400">*</span></label>
                  <UserSelect :roles="['办理人', '审批人']" single placeholder="请选择审批人" v-model="approverUserId" />
                </div>
                <!-- 0825 指派说明必填：写入工单日志，可导出 -->
                <div>
                  <label class="text-xs text-gray-500 block mb-1">指派说明 <span class="text-red-400">*</span></label>
                  <textarea v-model="approverNote" rows="3" placeholder="指派说明（必填，如客诉背景/优先处理原因/期望，将写入工单日志）..."
                    class="w-full px-3 py-2 border border-gray-300 rounded text-sm"></textarea>
                </div>
                <div class="flex flex-wrap gap-2">
                  <button @click="doAssignApprover" :disabled="approverSubmitting"
                    class="px-5 py-2 bg-primary text-white rounded text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition">
                    👤 {{ approverSubmitting ? '指派中...' : '确认指派审批人' }}
                  </button>
                  <!-- 0901 办理人不可承接退回：指派说明作为原因，确认弹窗防误触（复用 0826 审批人退回交互） -->
                  <button @click="askHandlerReject" :disabled="handlerRejectSubmitting"
                    class="px-4 py-2 bg-white border border-red-300 text-red-600 rounded text-sm font-medium hover:bg-red-50 disabled:opacity-50 transition">
                    🚫 {{ handlerRejectSubmitting ? '退回中...' : '不可承接，退回客服' }}
                  </button>
                </div>
                <div v-if="approverMsg" :class="['text-xs', approverOk ? 'text-green-600' : 'text-red-500']">{{ approverMsg }}</div>
              </div>
              <div v-else class="p-4 bg-amber-50 text-amber-800 rounded text-sm">等待办理人指派审批人…</div>
            </div>

            <!-- 指派承接人 → 审批人评估 + 多人指派 + 排期 -->
            <div v-else-if="complaint.status === '指派承接人'" class="space-y-3">
              <div v-if="isActingApprover || role === '管理员'" class="space-y-3">
                <div class="p-3 bg-orange-50 text-orange-800 rounded text-sm">
                  承接评估：填写可行性评估、预估工时、选择承接人（可多选，候选：办理人/审批人/承接人）与处理排期。
                </div>
                <!-- 0820 AI 分工建议 + AI 排期建议（恢复 0819 删除组件的 AI 部分，不做部门通知）
                     0821 合并为一个按钮：点击同时生成分工与排期，结果卡片上下排列（上分工、下排期） -->
                <div class="space-y-2">
                  <button type="button" @click="doAiDivisionAndSchedule"
                    :disabled="divisionLoading || scheduleLoading || !complaint.fault_phenomenon?.trim()"
                    class="w-full py-2.5 text-sm bg-gray-100 text-gray-700 hover:bg-gray-200 rounded-base disabled:opacity-50 transition font-normal">
                    {{ (divisionLoading || scheduleLoading) ? '⏳ AI 分析中...' : '🔍 AI 分工与排期建议（初步诊断 + 牵头/参与方向 + 预估工时）' }}
                  </button>
                  <!-- 分工建议结果（上） -->
                  <div v-if="divisionResult" class="p-3 bg-amber-50 border border-amber-200 rounded space-y-1.5 text-sm">
                    <p class="text-xs text-amber-600">AI 建议仅供参考，人员方向需审批人确认后指派实际承接人。</p>
                    <div><span class="font-medium">初步诊断：</span>{{ divisionResult.preliminary_diagnosis }}</div>
                    <div><span class="font-medium">牵头方向：</span>{{ divisionResult.lead_engineer }}</div>
                    <div v-if="divisionResult.participating_engineers?.length">
                      <span class="font-medium">参与方向：</span>
                      <span v-for="(p, idx) in divisionResult.participating_engineers" :key="idx"
                        class="inline-block mr-1 mb-1 px-2 py-0.5 rounded bg-white border border-amber-200 text-xs">{{ p }}</span>
                    </div>
                    <div><span class="font-medium">协同方案：</span>{{ divisionResult.collaboration_workflow }}</div>
                  </div>
                  <div v-if="divisionMsg" :class="['text-xs', divisionOk ? 'text-green-600' : 'text-red-500']">{{ divisionMsg }}</div>
                  <!-- 排期建议结果（下） -->
                  <div v-if="scheduleResult" class="p-3 bg-amber-50 border border-amber-200 rounded space-y-1 text-sm">
                    <div class="font-medium">建议工时：{{ scheduleResult.recommended_hours }} 小时
                      <span class="text-xs font-normal text-amber-700">（置信度：{{ scheduleResult.confidence }}<template v-if="scheduleResult.source === 'rules'"> · 规则兜底</template>）</span>
                      <button @click="applyScheduleHours" class="ml-2 px-2 py-0.5 bg-white border border-amber-300 rounded text-xs text-primary">应用到预估工时</button>
                    </div>
                    <div class="text-xs text-gray-600">{{ scheduleResult.reasoning }}</div>
                  </div>
                  <div v-if="scheduleMsg" :class="['text-xs', scheduleOk ? 'text-green-600' : 'text-red-500']">{{ scheduleMsg }}</div>
                </div>
                <div>
                  <label class="text-xs text-gray-500 block mb-1">评估意见 <span class="text-red-400">*</span></label>
                  <textarea v-model="assigneesForm.evaluation" rows="5" placeholder="评估内容（必填）：确认指派时作为承接可行性评估；不可承接退回时作为退回原因…"
                    class="w-full px-3 py-2 border border-gray-300 rounded text-sm"></textarea>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label class="text-xs text-gray-500 block mb-1">预估工时（h）<span class="text-red-400">*</span></label>
                    <input v-model.number="assigneesForm.estimatedHours" type="number" min="0.5" step="0.5"
                      class="w-full px-3 py-2 border border-gray-300 rounded text-sm" />
                  </div>
                  <div>
                    <label class="text-xs text-gray-500 block mb-1">计划开始</label>
                    <input v-model="assigneesForm.plannedStart" type="datetime-local"
                      class="w-full px-3 py-2 border border-gray-300 rounded text-sm" />
                  </div>
                  <div>
                    <label class="text-xs text-gray-500 block mb-1">计划结束</label>
                    <input v-model="assigneesForm.plannedEnd" type="datetime-local"
                      class="w-full px-3 py-2 border border-gray-300 rounded text-sm" />
                  </div>
                </div>
                <div>
                  <label class="text-xs text-gray-500 block mb-1">承接人（可多选）<span class="text-red-400">*</span></label>
                  <UserSelect :roles="['办理人', '审批人', '承接人']" inline-search v-model="assigneesForm.userIds"
                    @options-loaded="onAssigneeOptionsLoaded" />
                </div>
                <!-- 0820 主要推进人：从已选承接人中选一位 -->
                <div>
                  <label class="text-xs text-gray-500 block mb-1">主要推进人（从已选承接人中选一位，负责提交处理结果与回退）<span class="text-red-400">*</span></label>
                  <select v-model="assigneesForm.primaryUserId"
                    class="w-full px-3 py-2 border border-gray-300 rounded text-sm bg-white">
                    <option :value="0">请选择</option>
                    <option v-for="u in selectedAssigneeUsers" :key="u.id" :value="u.id">
                      {{ u.display_name }}（{{ u.position }}）
                    </option>
                  </select>
                </div>
                <!-- 冲突确认 -->
                <!-- 冲突提示：0820 去掉「仍要指派」按钮——提示即确认，再次点击「确认指派并转入处理」继续 -->
                <div v-if="assigneesConflictMsg" class="p-3 bg-yellow-50 border border-yellow-300 rounded text-sm text-yellow-800">
                  {{ assigneesConflictMsg }}
                </div>
                <div class="flex flex-wrap gap-3">
                  <button @click="doAssignAssignees" :disabled="assigneesSubmitting"
                    class="px-5 py-2 bg-primary text-white rounded text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition">
                    👥 {{ assigneesSubmitting ? '指派中...' : '确认指派并转入处理' }}
                  </button>
                  <!-- 0826 不可承接退回复用「评估意见」作为原因，经确认弹窗防误触，不再弹出独立输入面板 -->
                  <!-- 1020 退回改为申请制：须经王总/关总审批后才真正退回 -->
                  <button @click="askApproverReject" :disabled="!assigneesForm.evaluation.trim() || assigneesSubmitting || returnRequestPending"
                    class="px-5 py-2 border-2 border-red-400 text-red-600 rounded text-sm font-medium hover:bg-red-50 disabled:opacity-50 transition">
                    🚫 不可承接，申请退回（需王总/关总审批）
                  </button>
                </div>
                <div v-if="assigneesMsg" :class="['text-xs', assigneesOk ? 'text-green-600' : 'text-red-500']">{{ assigneesMsg }}</div>
              </div>
              <div v-else class="p-4 bg-orange-50 text-orange-800 rounded text-sm">{{ role === '审批人' ? '该工单当前由其他审批人跟进，您无操作权限' : '等待审批人评估与指派承接人…' }}</div>
            </div>

            <!-- 处理中 → 承接人/参与人进度；主要推进人提交结果/回退；审批人追加参与人/变更主要推进人 -->
            <div v-else-if="complaint.status === '处理中'" class="space-y-6">
              <template v-if="isCurrentAssignee || role === '管理员'">
                <ProgressUpdateForm :complaintId="complaint.id"
                  :plannedStart="complaint.planned_start_time || undefined" :plannedEnd="complaint.planned_end_time || undefined"
                  :latestProgress="progressInfo.latest" @done="reload" />
                <!-- 0820 非主要推进人提示：仅主要推进人可提交处理结果与回退 -->
                <div v-if="!isCurrentPrimary && role !== '管理员'"
                  class="p-3 bg-blue-50 text-blue-700 rounded text-sm">
                  您为参与人，可更新进度；提交处理结果与「处理不了」回退仅主要推进人可操作。
                </div>
              </template>
              <template v-if="isCurrentPrimary || role === '管理员'">
                <hr />
                <ResolutionForm :complaintId="complaint.id" :complaintNo="complaint.complaint_no" :initialSteps="complaint.reproduction_steps" @done="onActionDone('resolve')" />
                <!-- 处理不了回退 -->
                <div class="space-y-2">
                  <div class="text-sm font-medium text-gray-700">反馈处理不了（主要推进人，需审批人审批）</div>
                  <textarea v-model="cannotHandleReason" rows="3" placeholder="处理不了原因（必填）…"
                    class="w-full px-3 py-2 border border-gray-300 rounded text-sm"></textarea>
                  <!-- 1020 退回改为申请制：须经该工单当前审批人审批后才真正回退 -->
                  <button @click="doCannotHandle" :disabled="cannotHandleSubmitting || returnRequestPending"
                    class="px-4 py-2 bg-red-600 text-white rounded text-sm hover:bg-red-700 disabled:opacity-50 transition">
                    {{ cannotHandleSubmitting ? '提交中...' : '🚫 申请退回（需审批人审批）' }}
                  </button>
                  <div v-if="cannotHandleMsg" :class="['text-xs', cannotHandleOk ? 'text-green-600' : 'text-red-500']">{{ cannotHandleMsg }}</div>
                </div>
              </template>
              <!-- 0826 变更推进人/追加参与人功能相近：左右两列排列（移动端回落单列） -->
              <div v-if="isActingApprover || role === '管理员'" class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <!-- 0820 变更主要推进人 -->
                <div class="space-y-2 p-3 border border-violet-200 rounded">
                  <div class="text-sm font-medium text-gray-700">变更主要推进人</div>
                  <select v-model="primaryChangeUserId" class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm bg-white">
                    <option :value="0">请选择新的主要推进人</option>
                    <option v-for="a in workerAssignees" :key="a.user_id" :value="a.user_id">
                      {{ a.display_name }}（{{ a.position }}）{{ a.is_primary === 1 ? '· 当前' : '' }}
                    </option>
                  </select>
                  <button @click="openConfirmPrimary" :disabled="primarySubmitting"
                    class="px-4 py-2 bg-violet-600 text-white rounded text-sm hover:bg-violet-700 disabled:opacity-50 transition">
                    👑 {{ primarySubmitting ? '变更中...' : '确认变更' }}
                  </button>
                  <div v-if="primaryMsg" :class="['text-xs', primaryOk ? 'text-green-600' : 'text-red-500']">{{ primaryMsg }}</div>
                </div>
                <div class="space-y-2 p-3 border border-cyan-200 rounded">
                  <div class="text-sm font-medium text-gray-700">追加参与人（候选：办理人/审批人/承接人）</div>
                  <UserSelect :roles="['办理人', '审批人', '承接人']" inline-search v-model="participantIds" />
                  <button @click="openConfirmParticipants" :disabled="participantSubmitting"
                    class="px-4 py-2 bg-cyan-600 text-white rounded text-sm hover:bg-cyan-700 disabled:opacity-50 transition">
                    🤝 {{ participantSubmitting ? '添加中...' : '确认追加' }}
                  </button>
                  <div v-if="participantMsg" :class="['text-xs', participantOk ? 'text-green-600' : 'text-red-500']">{{ participantMsg }}</div>
                </div>
              </div>
              <div v-if="!isCurrentAssignee && role !== '管理员' && !isActingApprover"
                class="p-4 bg-yellow-50 text-yellow-800 rounded text-sm">
                {{ role === '审批人' ? '该工单当前由其他审批人跟进，您无操作权限' : '仅该工单的承接人/参与人可更新进度；主要推进人可提交方案与回退。' }}
              </div>
            </div>

            <!-- 已关闭 -->
            <div v-else-if="complaint.status === '已关闭'" class="p-4 bg-green-50 text-green-800 rounded text-sm">
              此工单已关闭
              <div class="mt-2 space-y-1 text-xs">
                <div>关闭时间：{{ complaint.closed_at }}</div>
                <div>办理人：{{ complaint.handler_name || '-' }}</div>
                <div>预计工时：{{ complaint.estimated_hours || 0 }}h</div>
              </div>
            </div>

            <!-- 已撤回（0825 终态；0826 起由录入客服在看板发起撤回） -->
            <div v-else-if="complaint.status === '已撤回'" class="p-4 bg-stone-50 text-stone-700 rounded text-sm">
              此工单已被录入客服撤回（终态，未归档知识库；如需恢复请联系管理员调整状态）
              <div class="mt-2 text-xs">撤回详情可查看下方工单日志或备注。</div>
            </div>

            <!-- 默认提示（0820 友好化：管理员改状态等状态/子类型组合不匹配任何分支时落入此处） -->
            <div v-else class="p-4 bg-gray-50 text-gray-600 rounded text-sm text-center">
              工单当前状态为「{{ complaint.status }}」，此阶段暂无对应操作，进展可查看下方工单日志。
            </div>

            </template><!-- /awaitingFeedback 冻结操作区 -->

            <!-- 0731 评价卡片 — 独立于状态 v-if 分支，不会被销毁；仅提交/关闭后刷新到新状态 -->
            <div id="ai-feedback-card">
              <FeedbackCard
                v-if="feedbackTarget.complaintNo && feedbackTarget.feedbackType"
                :complaintNo="feedbackTarget.complaintNo"
                :feedbackType="feedbackTarget.feedbackType"
                :complaintContext="complaint ? {
                  fault_category: complaint.fault_category || '',
                  equipment_model: complaint.equipment_model || '',
                  status: complaint.status || '',
                  responsible_dept: '',
                } : null"
                :aiSuggestion="aiSuggestion.current"
                @submitted="onFeedbackDone()"
                @dismissed="onFeedbackDone()"
              />
            </div>
          </div>

        </template>
      </div>
    </div>

    <!-- 0819 编辑工单弹窗（rework 分支 / 管理员编辑） -->
    <EditComplaintModal :visible="!!store.editTargetId"
      :complaint="editTargetComplaint"
      :canEditPriority="role === '管理员'"
      @close="store.closeModals()"
      @save="onSaveEdit" />

    <!-- 0820 确认弹窗：变更主要推进人 / 追加参与人 -->
    <ConfirmDialog :visible="confirmPrimaryVisible"
      title="确认变更主要推进人"
      :message="primaryConfirmMessage"
      confirmText="确认变更"
      confirmClass="bg-violet-600 hover:bg-violet-700"
      :loading="primarySubmitting"
      @confirm="onConfirmPrimary"
      @cancel="confirmPrimaryVisible = false" />
    <ConfirmDialog :visible="confirmParticipantsVisible"
      title="确认追加参与人"
      :message="participantsConfirmMessage"
      confirmText="确认追加"
      confirmClass="bg-cyan-600 hover:bg-cyan-700"
      :loading="participantSubmitting"
      @confirm="onConfirmParticipants"
      @cancel="confirmParticipantsVisible = false" />

    <!-- 0826 客诉审核拒绝确认：评估内容作为拒绝原因提交，优先级/去向不生效 -->
    <ConfirmDialog :visible="intakeRejectConfirm"
      title="确认拒绝该工单"
      message="工单将退回客服修改（重新提交后需再次审核）。当前审核评估内容将作为拒绝原因提交；已选择的优先级与去向不会生效。"
      confirmText="确认拒绝"
      :loading="intakeSubmitting"
      @confirm="doIntakeReject"
      @cancel="intakeRejectConfirm = false" />

    <!-- 0826 审批人不可承接退回确认：评估意见作为原因提交，工时/排期/承接人不生效 -->
    <ConfirmDialog :visible="approverRejectConfirm"
      title="确认退回工单"
      message="工单将退回办理人重新指派。当前评估意见将作为不可承接原因提交；已填写的工时、排期与承接人选择不会生效。"
      confirmText="确认退回"
      :loading="assigneesSubmitting"
      @confirm="doApproverReject"
      @cancel="approverRejectConfirm = false" />

    <!-- 0901 办理人不可承接退回确认：指派说明作为原因提交，退回归录客服（修改重提或撤回） -->
    <ConfirmDialog :visible="handlerRejectConfirm"
      title="确认退回客服"
      message="工单将退回录入客服（待客服处理），由客服修改后重新提交审核或撤回。当前指派说明将作为不可承接原因提交；已选择的审批人不会生效。"
      confirmText="确认退回"
      :loading="handlerRejectSubmitting"
      @confirm="doHandlerReject"
      @cancel="handlerRejectConfirm = false" />

    <!-- 0826 附件删除确认 -->
    <ConfirmDialog :visible="!!attachmentDeleteTarget"
      title="确认删除附件"
      :message="`确定要删除附件「${attachmentDeleteTarget?.filename}」吗？删除后不可恢复。`"
      confirmText="确认删除"
      :loading="attachmentDeleting"
      @confirm="doDeleteAttachment"
      @cancel="attachmentDeleteTarget = null" />

    <!-- 1016 预警弹窗：关键词多选（两档）+ 可选备注 -->
    <Teleport to="body">
      <div v-if="warningVisible" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-black/40" @click="warningVisible = false"></div>
        <div class="relative bg-white rounded-lg shadow-xl w-full max-w-lg mx-4 max-h-[85vh] overflow-y-auto p-5 space-y-4">
          <div class="flex items-center justify-between">
            <h3 class="font-semibold">⚠️ 发起工单预警</h3>
            <button type="button" @click="warningVisible = false" class="text-gray-400 hover:text-gray-600"><X :size="18" /></button>
          </div>
          <div class="text-xs text-gray-500">
            低风险 → 通知客服主管与承办人（承接人）；高风险 → 在上述基础上额外知会
            {{ HIGH_RISK_WATCHERS.join('、') }}。可多选。
          </div>
          <div class="space-y-2">
            <div class="text-xs font-medium text-gray-600">低风险</div>
            <div class="flex flex-wrap gap-2">
              <button v-for="k in WARNING_KEYWORDS_LOW" :key="k" type="button" @click="toggleWarningKeyword(k)"
                :class="['px-3 py-1.5 rounded-base text-sm border transition',
                  warningKeywords.includes(k) ? 'bg-amber-500 text-white border-amber-500' : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50']">
                {{ k }}
              </button>
            </div>
            <div class="text-xs font-medium text-gray-600 pt-1">高风险（触发加发指定知会人）</div>
            <div class="flex flex-wrap gap-2">
              <button v-for="k in WARNING_KEYWORDS_HIGH" :key="k" type="button" @click="toggleWarningKeyword(k)"
                :class="['px-3 py-1.5 rounded-base text-sm border transition',
                  warningKeywords.includes(k) ? 'bg-red-600 text-white border-red-600' : 'bg-white text-red-700 border-red-300 hover:bg-red-50']">
                {{ k }}
              </button>
            </div>
          </div>
          <div>
            <label class="text-xs text-gray-500 block mb-1">补充说明（选填）</label>
            <textarea v-model="warningNote" rows="3" placeholder="如：客户已明确表示若本周未解决将退机…"
              class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm focus:ring-2 focus:ring-amber-300"></textarea>
          </div>
          <div v-if="warningError" class="text-xs text-red-600">{{ warningError }}</div>
          <div class="flex justify-end gap-2">
            <button type="button" @click="warningVisible = false"
              class="px-4 py-1.5 bg-gray-100 text-gray-700 rounded-base hover:bg-gray-200 text-sm">取消</button>
            <button type="button" @click="doRaiseWarning" :disabled="!warningKeywords.length || warningSending"
              class="px-4 py-1.5 bg-amber-600 text-white rounded-base hover:bg-amber-700 disabled:opacity-50 text-sm font-medium">
              {{ warningSending ? '发送中…' : '发送预警' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

  </AppLayout>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useComplaintsStore } from '@/stores/complaints'
import AppLayout from '@/components/layout/AppLayout.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import PriorityBadge from '@/components/common/PriorityBadge.vue'
import UserSelect from '@/components/common/UserSelect.vue'
import EditComplaintModal from '@/components/complaint/EditComplaintModal.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import WorkOrderTimeline from '@/components/complaint/WorkOrderTimeline.vue'
import ProgressUpdateForm from '@/components/complaint/ProgressUpdateForm.vue'
import ResolutionForm from '@/components/complaint/ResolutionForm.vue'
import CustomerConfirmForm from '@/components/complaint/CustomerConfirmForm.vue'
import FeedbackCard from '@/components/common/FeedbackCard.vue'
import CaseCard from '@/components/complaint/CaseCard.vue'
import apiClient from '@/api/client'
import { ArrowLeft, ChevronDown, X } from 'lucide-vue-next'
import { searchSimilarCases, findSimilarCasesQuick, getChecklist, getSelfCheckSuggestions, diagnoseComplaint, getScheduleSuggestion } from '@/api/ai'
import { getPendingFeedback } from '@/api/feedback'
import { aiSuggestion } from '@/composables/aiTracker'
import { onWsEvent } from '@/composables/useWebSocket'
import { parseReturnNote } from '@/utils/complaintReturn'
import { formatDateTime } from '@/utils/datetime'
import { bigramDice, AI_ADOPTION_MATCH_THRESHOLD } from '@/utils/textSimilarity'
import { WARNING_KEYWORDS_LOW, WARNING_KEYWORDS_HIGH, HIGH_RISK_WATCHERS, RETURN_APPROVERS } from '@/types/api'
import {
  intakeReview, resubmitComplaint, submitInvestigationResult,
  assignApprover as assignApproverApi, approverReject as approverRejectApi,
  handlerReject as handlerRejectApi,
  assignAssignees as assignAssigneesApi, addParticipants as addParticipantsApi,
  cannotHandle as cannotHandleApi, saveRemark, reviewEmail,
  setPrimaryAssignee, getComplaintBriefsByIds,
  raiseWarning, reviewReturn,
} from '@/api/complaints'
import type { Complaint, Attachment, UserOption, ComplaintBrief } from '@/types/api'
import { equipmentSnLabel } from '@/types/api'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const store = useComplaintsStore()
const role = computed(() => auth.role || '')

// 0901 退回来源（主管/办理人姓名）解析：主管退回显示「主管退回原因」，办理人退回显示「办理人 张三 退回原因」
const returnNote = computed(() => parseReturnNote(complaint.value?.supervisor_rejection_note))
// 0819 移动端视图判断（<768px）：影响列表/详情显隐与导航方式
const isMobileView = () => !window.matchMedia('(min-width: 768px)').matches

// 0819 当前用户是否为该工单的有效承接人/参与人（处理中操作区权限）
const isCurrentAssignee = computed(() => {
  const list = complaint.value?.assignees || []
  return list.some(a => a.assignee_type === 'assignee' && a.user_id === auth.user?.id)
})

// 0820 当前用户是否为该工单的主要推进人（提交处理结果/回退权限）
const isCurrentPrimary = computed(() => {
  const list = complaint.value?.assignees || []
  return list.some(a => a.assignee_type === 'assignee' && a.is_primary === 1 && a.user_id === auth.user?.id)
})

// 0821 当前用户是否为该工单的当前审批人（审批人操作隔离）
const isCurrentApprover = computed(() => {
  const list = complaint.value?.assignees || []
  return list.some(a => a.assignee_type === 'approver' && a.user_id === auth.user?.id)
})

// 0825 办理人可被指派为审批人：绑定当前审批人且角色为审批人/办理人时，可执行审批人操作
const isActingApprover = computed(() =>
  isCurrentApprover.value && (role.value === '审批人' || role.value === '办理人')
)

// 0821 当前用户是否为该工单的录入客服（客服操作隔离）
const isCreator = computed(() => {
  const uid = complaint.value?.created_by_user_id
  return !!uid && uid === auth.user?.id
})

// 0820 变更主要推进人候选：当前有效承接人/参与人
const workerAssignees = computed(() =>
  (complaint.value?.assignees || []).filter(a => a.assignee_type === 'assignee')
)

// 0819 指派行摘要（审批人 + 承接人/参与人，含职位；0820 主要推进人用 [主] 标记）
const assigneeSummary = computed(() => {
  const list = complaint.value?.assignees || []
  if (!list.length) return ''
  const fmt = (a: any) => `${a.display_name}${a.is_primary === 1 ? '[主]' : ''}（${a.role}${a.position ? '·' + a.position : ''}）`
  const approvers = list.filter(a => a.assignee_type === 'approver').map(fmt)
  const workers = list.filter(a => a.assignee_type === 'assignee').map(fmt)
  const parts: string[] = []
  if (approvers.length) parts.push(`审批:${approvers.join('、')}`)
  if (workers.length) parts.push(`承接:${workers.join('、')}`)
  return parts.join('　')
})

// 0819 v3.0 状态机操作区状态
const intakeForm = reactive({ priority: '', route: '', evaluation: '' })
// 0826 统一评估框：拒绝复用 intakeForm.evaluation，经确认弹窗防误触（撤回已移至看板，录入客服操作）
const intakeRejectConfirm = ref(false)
const intakeSubmitting = ref(false)
const intakeMsg = ref('')
const intakeOk = ref(false)
// 0820 审核评估 AI 自排查推荐（复用客诉录入链路）
const intakeSelfCheckLoading = ref(false)
const intakeSelfCheckSuccess = ref(false)

const resubmitLoading = ref(false)
const resubmitMsg = ref('')
const resubmitOk = ref(false)

const investigationRemark = ref('')
const investigationSubmitting = ref<'' | 'resolved' | 'unresolved'>('')
const investigationMsg = ref('')
const investigationOk = ref(false)

const approverUserId = ref<number>(0)
const approverNote = ref('')   // 0825 指派说明（必填，写日志）
const approverSubmitting = ref(false)
const approverMsg = ref('')
const approverOk = ref(false)

const assigneesForm = reactive({
  evaluation: '', estimatedHours: 0, userIds: [] as number[],
  plannedStart: '', plannedEnd: '',
  primaryUserId: 0,  // 0820 主要推进人（必选，∈ userIds）
})
// 0820 承接人候选选项（UserSelect options-loaded 事件维护，用于主要推进人姓名映射）
const assigneeOptions = ref<UserOption[]>([])
function onAssigneeOptionsLoaded(users: UserOption[]) {
  assigneeOptions.value = users
}
const selectedAssigneeUsers = computed(() =>
  assigneeOptions.value.filter(u => assigneesForm.userIds.includes(u.id))
)
// 已选承接人变化时，若主要推进人不在其中则清空
watch(() => assigneesForm.userIds, (ids) => {
  if (assigneesForm.primaryUserId && !ids.includes(assigneesForm.primaryUserId)) {
    assigneesForm.primaryUserId = 0
  }
})
const assigneesSubmitting = ref(false)
const assigneesForce = ref(false)
const assigneesConflictMsg = ref('')
const assigneesMsg = ref('')
const assigneesOk = ref(false)
// 0826 不可承接退回确认（评估意见将作为退回原因，工时/排期/承接人不提交）
const approverRejectConfirm = ref(false)

const cannotHandleReason = ref('')
const cannotHandleSubmitting = ref(false)
const cannotHandleMsg = ref('')
const cannotHandleOk = ref(false)

const participantIds = ref<number[]>([])
const participantSubmitting = ref(false)
const participantMsg = ref('')
const participantOk = ref(false)

// 0820 变更主要推进人（审批人/管理员，处理中）
const primaryChangeUserId = ref<number>(0)
const primarySubmitting = ref(false)
const primaryMsg = ref('')
const primaryOk = ref(false)
// 0820 确认弹窗：变更主要推进人 / 追加参与人
const confirmPrimaryVisible = ref(false)
const confirmParticipantsVisible = ref(false)
const primaryConfirmMessage = computed(() => {
  const target = workerAssignees.value.find(a => a.user_id === primaryChangeUserId.value)
  const current = workerAssignees.value.find(a => a.is_primary === 1)
  return `确定将主要推进人变更为「${target?.display_name || '—'}」吗？变更后仅新的主要推进人可提交处理结果与回退。${current && current.user_id !== primaryChangeUserId.value ? `（当前：${current.display_name}）` : ''}`
})
const participantsConfirmMessage = computed(() => {
  const names = assigneeOptions.value.filter(u => participantIds.value.includes(u.id)).map(u => u.display_name)
  return `确定追加参与人「${names.join('、') || '—'}」吗？追加后他们可更新进度，但不能提交处理结果与回退。`
})
function openConfirmPrimary() {
  if (!primaryChangeUserId.value) { primaryOk.value = false; primaryMsg.value = '请选择新的主要推进人'; return }
  confirmPrimaryVisible.value = true
}
function openConfirmParticipants() {
  if (!participantIds.value.length) { participantOk.value = false; participantMsg.value = '请选择参与人'; return }
  confirmParticipantsVisible.value = true
}
async function onConfirmPrimary() {
  confirmPrimaryVisible.value = false
  await doSetPrimary()
}
async function onConfirmParticipants() {
  confirmParticipantsVisible.value = false
  await doAddParticipants()
}

// 0820 AI 分工建议 / AI 排期建议（指派承接人操作区）
const divisionLoading = ref(false)
const divisionResult = ref<{
  preliminary_diagnosis: string; lead_engineer: string
  participating_engineers: string[]; collaboration_workflow: string
} | null>(null)
const divisionMsg = ref('')
const divisionOk = ref(false)
const scheduleLoading = ref(false)
const scheduleResult = ref<{
  recommended_hours: number; reasoning: string; confidence: string; source: string
} | null>(null)
const scheduleMsg = ref('')
const scheduleOk = ref(false)

const activeId = ref<number | null>(null)
const complaint = ref<Complaint | null>(null)
// 0821 AI 智能辅助面板折叠（仅「指派承接人」状态可折叠，默认折叠；其他状态恒展开）
const aiPanelCollapsed = ref(true)
const isAssigneeAssignmentStatus = computed(() => complaint.value?.status === '指派承接人')
watch(
  () => (complaint.value ? `${complaint.value.id}|${complaint.value.status}` : ''),
  () => { aiPanelCollapsed.value = complaint.value?.status === '指派承接人' },
)
// 0729 评价卡片独立生命周期（不受 v-if 分支销毁影响）
const feedbackTarget = ref<{ complaintNo: string; feedbackType: string }>({ complaintNo: '', feedbackType: '' })
// 0731 评价卡片显示期间冻结操作区：用户必须先完成/关闭评价卡片才能看到新状态的操作区
const awaitingFeedback = ref(false)

// ── 1020 退回审批 ──
const returnReviewNote = ref('')
const returnReviewing = ref(false)
const returnReviewMsg = ref('')
const returnReviewOk = ref(false)
const returnRequestPending = computed(() => complaint.value?.return_request_status === 'pending')
const returnTypeLabel = computed(() =>
  complaint.value?.return_request_type === 'cannot_handle' ? '承接人处理不了' : '审批人不可承接'
)
const returnReviewerLabel = computed(() =>
  complaint.value?.return_request_type === 'cannot_handle' ? '审批人' : '王总/关总'
)
const canReviewReturn = computed(() => {
  if (!returnRequestPending.value || !complaint.value) return false
  // 不能审批自己发起的申请
  if (complaint.value.return_request_by_id && complaint.value.return_request_by_id === auth.user?.id) return false
  if (role.value === '管理员') return true
  if (complaint.value.return_request_type === 'cannot_handle') return isActingApprover.value
  if (complaint.value.return_request_type === 'approver_reject') {
    return RETURN_APPROVERS.includes(auth.displayName || '')
  }
  return false
})

async function doReviewReturn(action: 'approved' | 'rejected') {
  if (!complaint.value) return
  returnReviewing.value = true
  returnReviewMsg.value = ''
  try {
    const r = await reviewReturn(complaint.value.id, { action, note: returnReviewNote.value.trim() })
    if (r.data?.success) {
      returnReviewOk.value = true
      returnReviewMsg.value = r.data.message || (action === 'approved' ? '已同意退回' : '已驳回')
      returnReviewNote.value = ''
      await reload()
    } else {
      returnReviewOk.value = false
      returnReviewMsg.value = r.data?.message || '审批失败'
    }
  } catch (e: any) {
    returnReviewOk.value = false
    returnReviewMsg.value = e?.response?.data?.detail || '审批失败'
  } finally {
    returnReviewing.value = false
  }
}

// ── 1016 工单预警 ──
const warningVisible = ref(false)
const warningKeywords = ref<string[]>([])
const warningNote = ref('')
const warningSending = ref(false)
const warningMsg = ref('')
const warningOk = ref(false)
const warningError = ref('')
// 客服/客服主管发起（管理员按惯例一并放开）；已关闭/已撤回无预警意义
const canRaiseWarning = computed(() =>
  ['客服', '客服主管', '管理员'].includes(role.value) &&
  !!complaint.value && !['已关闭', '已撤回'].includes(complaint.value.status || '')
)

function openWarning() {
  warningKeywords.value = []
  warningNote.value = ''
  warningError.value = ''
  warningMsg.value = ''
  warningVisible.value = true
}

function toggleWarningKeyword(k: string) {
  const i = warningKeywords.value.indexOf(k)
  if (i >= 0) warningKeywords.value.splice(i, 1)
  else warningKeywords.value.push(k)
}

async function doRaiseWarning() {
  if (!complaint.value || !warningKeywords.value.length) return
  warningSending.value = true
  warningError.value = ''
  try {
    const r = await raiseWarning(complaint.value.id, {
      keywords: [...warningKeywords.value],
      note: warningNote.value.trim(),
    })
    if (r.data?.success && r.data.data) {
      const d = r.data.data
      warningVisible.value = false
      warningOk.value = true
      warningMsg.value = r.data.message || `预警已发出（${d.tier === 'high' ? '高风险' : '低风险'}档）`
        + (d.missing?.length ? `；${d.missing.join('、')} 未找到用户，未通知` : '')
      reload()
    } else {
      warningError.value = r.data?.message || '预警发送失败'
    }
  } catch (e: any) {
    warningError.value = e?.response?.data?.detail || '预警发送失败'
  } finally {
    warningSending.value = false
  }
}
const options = ref<Array<{ id: number; complaint_no: string; customer_name: string; status: string; fault_category?: string; equipment_sn?: string; _planned_end_time?: string; _expected_complete_date?: string; _status?: string; _my_roles?: string[] }>>([])
const filteredOptions = ref<typeof options.value>([])
const searchKeyword = ref('')
// 0820 客服/客服主管/办理人/审批人/承接人默认勾选（两层筛选由后端按角色决定）
const myOrdersOnly = ref(['客服', '客服主管', '办理人', '审批人', '承接人'].includes(auth.role || ''))
const listLoading = ref(false)
const listError = ref('')
const detailLoading = ref(false)
// 0803 手动 reload 后短时间内抑制 WebSocket 刷新，避免双重渲染闪烁（审核通过/拒绝等操作）
const reloadingGate = ref(false)

const attachments = ref<Attachment[]>([])
const previewImage = ref<Attachment | null>(null)
const tokenParam = computed(() => {
  const t = sessionStorage.getItem('token') || ''
  return t ? `?token=${encodeURIComponent(t)}` : ''
})

// 0826 附件删除（对齐后端 user_can_manage_files 权限）：管理员/录入客服/当前审批人/有效承接人
const canManageFiles = computed(() =>
  role.value === '管理员' ||
  (role.value === '客服' && isCreator.value) ||
  isActingApprover.value ||
  isCurrentAssignee.value
)
const attachmentDeleteTarget = ref<Attachment | null>(null)
const attachmentDeleting = ref(false)
const attachmentMsg = ref('')

async function doDeleteAttachment() {
  const att = attachmentDeleteTarget.value
  if (!att) return
  attachmentDeleting.value = true
  try {
    const r = await apiClient.delete(`/api/files/${att.id}`)
    if (r.data?.success) {
      attachments.value = attachments.value.filter(a => a.id !== att.id)
      attachmentDeleteTarget.value = null
      attachmentMsg.value = ''
    } else {
      attachmentMsg.value = r.data?.message || '删除失败'
    }
  } catch (e: any) {
    attachmentMsg.value = e?.response?.data?.detail || '删除失败'
  } finally { attachmentDeleting.value = false }
}

// 0803 统一工单时间线
const timelineLogs = ref<import('@/types/api').WorkOrderLogEntry[]>([])
const progressInfo = reactive({ pct: 0, method: '', latest: null as any })
const progressHistory = ref<any[]>([])
const processingHours = ref('')


// 0804 邮件审核操作（详情页）
const emailReviewLoading = ref(false)
const emailReviewMsg = ref('')
const emailReviewOk = ref(false)
const emailRejectMode = ref(false)
const emailRejectNote = ref('')
const emailDraft = computed(() => {
  const raw = complaint.value?.email_draft_content
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
})

async function doEmailApprove() {
  if (!activeId.value) return
  emailReviewLoading.value = true; emailReviewMsg.value = ''
  try {
    const r = await reviewEmail(activeId.value, 'approved')
    if (r.data?.success) {
      emailReviewOk.value = true; emailReviewMsg.value = '已批准发送'
      await reload()
    } else {
      emailReviewOk.value = false; emailReviewMsg.value = r.data?.message || '操作失败'
    }
  } catch (e: any) {
    emailReviewOk.value = false
    emailReviewMsg.value = e?.response?.data?.detail || '操作失败'
  } finally { emailReviewLoading.value = false }
}

async function doEmailReject() {
  if (!activeId.value) return
  emailReviewLoading.value = true; emailReviewMsg.value = ''
  try {
    const r = await reviewEmail(activeId.value, 'rejected', emailRejectNote.value.trim() || undefined)
    if (r.data?.success) {
      emailReviewOk.value = true; emailReviewMsg.value = '已拒绝，客服将收到通知'
      emailRejectMode.value = false; emailRejectNote.value = ''
      await reload()
    } else {
      emailReviewOk.value = false; emailReviewMsg.value = r.data?.message || '操作失败'
    }
  } catch (e: any) {
    emailReviewOk.value = false
    emailReviewMsg.value = e?.response?.data?.detail || '操作失败'
  } finally { emailReviewLoading.value = false }
}

// ═══════════ 0819 v3.0 新状态机处理函数 ═══════════

// 编辑弹窗（rework 分支 / 管理员）
const editTargetComplaint = computed(() =>
  complaint.value?.id === store.editTargetId ? complaint.value : null
)

async function onSaveEdit(data: Record<string, any>) {
  if (!store.editTargetId) return
  await store.update(store.editTargetId, data)
  store.closeModals()
  await reload()
}

// 0902 AI 采纳埋点快照：绑定 complaint_no，切单后自动失效（no 不匹配即不比对），避免串单
const aiIntakeEvalSuggest = ref<{ no: string; text: string } | null>(null)
const aiDivisionSuggest = ref<{ no: string; text: string } | null>(null)

// 0820 审核评估 AI 自排查推荐（复用客诉录入 doSelfCheck 逻辑）
async function doIntakeSelfCheck() {
  if (!complaint.value?.fault_phenomenon?.trim()) return
  intakeSelfCheckLoading.value = true
  try {
    const r = await getSelfCheckSuggestions(complaint.value.fault_phenomenon.trim(), complaint.value.equipment_model?.trim() || '')
    if (r.data?.success && r.data.data) {
      const d = r.data.data
      const lines: string[] = []
      if (d.summary) lines.push(`${d.summary}`)
      if (d.suggestions?.length) {
        lines.push('')
        d.suggestions.forEach((s: string) => { lines.push(s) })
      }
      intakeForm.evaluation = lines.join('\n')
      intakeSelfCheckSuccess.value = true
      // 0820 写入 AI 建议文本，供审核通过后的 evaluate 评价卡携带
      aiSuggestion.current = lines.join('\n')
      aiIntakeEvalSuggest.value = { no: complaint.value?.complaint_no || '', text: lines.join('\n') }
    }
  } catch (e: any) {
    console.error('intake self-check error:', e)
    intakeOk.value = false; intakeMsg.value = 'AI 服务暂不可用，请手动填写审核评估'
  } finally {
    intakeSelfCheckLoading.value = false
  }
}

async function doIntakeApprove() {
  if (!activeId.value) return
  if (!intakeForm.priority) { intakeOk.value = false; intakeMsg.value = '请选择优先级（P0-P3）'; return }
  if (!intakeForm.route) { intakeOk.value = false; intakeMsg.value = '请选择通过后去向'; return }
  // 0820 审核通过也必须填写审核评估
  if (!intakeForm.evaluation.trim()) { intakeOk.value = false; intakeMsg.value = '请填写客服主管审核评估（可点击上方 AI 生成）'; return }
  intakeSubmitting.value = true; intakeMsg.value = ''
  try {
    const r = await intakeReview(activeId.value, {
      action: 'approve', priority: intakeForm.priority, route: intakeForm.route,
      evaluation: intakeForm.evaluation.trim(),
    })
    if (r.data?.success) {
      intakeOk.value = true; intakeMsg.value = r.data?.message || '审核通过'
      // 0902 AI 采纳：审核评估 vs AI 自排查建议的匹配度（清空前比对；快照绑定单号防串单）
      const intakeSuggest = aiIntakeEvalSuggest.value
      if (intakeSuggest && intakeSuggest.no === (complaint.value?.complaint_no || '')) {
        const sim = bigramDice(intakeSuggest.text, intakeForm.evaluation.trim())
        import('@/api/eval').then(m => {
          m.recordAiAdoption(intakeSuggest.no, 'self_check', intakeSuggest.text.slice(0, 500), sim >= AI_ADOPTION_MATCH_THRESHOLD, sim)
        }).catch(() => {})
      }
      aiIntakeEvalSuggest.value = null
      intakeForm.evaluation = ''
      intakeSelfCheckSuccess.value = false
      // 0820 审核通过后弹出 evaluate 评价卡（提交后 onFeedbackDone 自动 reload 并跳下一单）
      onActionDone('evaluate')
    } else {
      intakeOk.value = false; intakeMsg.value = r.data?.message || '操作失败'
    }
  } catch (e: any) {
    intakeOk.value = false; intakeMsg.value = e?.response?.data?.detail || '操作失败'
  } finally { intakeSubmitting.value = false }
}

// 0826 拒绝入口：校验评估非空后弹确认（评估内容将作为拒绝原因，优先级/去向不提交）
function askIntakeReject() {
  if (!intakeForm.evaluation.trim()) {
    intakeOk.value = false; intakeMsg.value = '请先填写审核评估（拒绝时将作为拒绝原因提交）'
    return
  }
  intakeRejectConfirm.value = true
}

async function doIntakeReject() {
  if (!activeId.value || !intakeForm.evaluation.trim()) return
  intakeSubmitting.value = true; intakeMsg.value = ''
  try {
    const r = await intakeReview(activeId.value, {
      action: 'reject', rejection_note: intakeForm.evaluation.trim(),
    })
    if (r.data?.success) {
      intakeOk.value = true; intakeMsg.value = '已拒绝，退回客服修改'
      intakeRejectConfirm.value = false
      // 0902 AI 采纳：拒绝原因沿用评估文本，与 AI 自排查建议比对（口径与审核通过一致）
      const intakeSuggest = aiIntakeEvalSuggest.value
      if (intakeSuggest && intakeSuggest.no === (complaint.value?.complaint_no || '')) {
        const sim = bigramDice(intakeSuggest.text, intakeForm.evaluation.trim())
        import('@/api/eval').then(m => {
          m.recordAiAdoption(intakeSuggest.no, 'self_check', intakeSuggest.text.slice(0, 500), sim >= AI_ADOPTION_MATCH_THRESHOLD, sim)
        }).catch(() => {})
      }
      aiIntakeEvalSuggest.value = null
      intakeForm.evaluation = ''
      await reload()
    } else {
      intakeOk.value = false; intakeMsg.value = r.data?.message || '操作失败'
    }
  } catch (e: any) {
    intakeOk.value = false; intakeMsg.value = e?.response?.data?.detail || '操作失败'
  } finally { intakeSubmitting.value = false }
}

async function doResubmit() {
  if (!activeId.value) return
  resubmitLoading.value = true; resubmitMsg.value = ''
  try {
    const r = await resubmitComplaint(activeId.value)
    if (r.data?.success) {
      resubmitOk.value = true; resubmitMsg.value = r.data?.message || '已重新提交审核'
      await reload()
    } else {
      resubmitOk.value = false; resubmitMsg.value = r.data?.message || '操作失败'
    }
  } catch (e: any) {
    resubmitOk.value = false; resubmitMsg.value = e?.response?.data?.detail || '操作失败'
  } finally { resubmitLoading.value = false }
}

async function doInvestigation(result: 'resolved' | 'unresolved') {
  if (!activeId.value) return
  investigationSubmitting.value = result; investigationMsg.value = ''
  try {
    const r = await submitInvestigationResult(activeId.value, result, investigationRemark.value.trim())
    if (r.data?.success) {
      investigationOk.value = true; investigationMsg.value = r.data?.message || '排查结果已提交'
      investigationRemark.value = ''
      await reload()
    } else {
      investigationOk.value = false; investigationMsg.value = r.data?.message || '操作失败'
    }
  } catch (e: any) {
    investigationOk.value = false; investigationMsg.value = e?.response?.data?.detail || '操作失败'
  } finally { investigationSubmitting.value = '' }
}

async function doAssignApprover() {
  if (!activeId.value || !approverUserId.value) {
    approverOk.value = false; approverMsg.value = '请选择审批人'; return
  }
  // 0825 指派说明必填（写工单日志）
  if (!approverNote.value.trim()) {
    approverOk.value = false; approverMsg.value = '请填写指派说明'; return
  }
  approverSubmitting.value = true; approverMsg.value = ''
  try {
    const r = await assignApproverApi(activeId.value, approverUserId.value, approverNote.value.trim())
    if (r.data?.success) {
      approverOk.value = true; approverMsg.value = r.data?.message || '已指派审批人'
      await reload()
    } else {
      approverOk.value = false; approverMsg.value = r.data?.message || '指派失败'
    }
  } catch (e: any) {
    approverOk.value = false; approverMsg.value = e?.response?.data?.detail || '指派失败'
  } finally { approverSubmitting.value = false }
}

// 0826 退回入口：校验评估意见非空后弹确认
function askApproverReject() {
  if (!assigneesForm.evaluation.trim()) {
    assigneesOk.value = false; assigneesMsg.value = '请先填写评估意见（退回时将作为不可承接原因提交）'
    return
  }
  approverRejectConfirm.value = true
}

async function doApproverReject() {
  if (!activeId.value || !assigneesForm.evaluation.trim()) return
  assigneesSubmitting.value = true; assigneesMsg.value = ''
  try {
    const r = await approverRejectApi(activeId.value, assigneesForm.evaluation.trim())
    if (r.data?.success) {
      assigneesOk.value = true; assigneesMsg.value = r.data?.message || '已退回'
      approverRejectConfirm.value = false
      assigneesForm.evaluation = ''
      await reload()
    } else {
      assigneesOk.value = false; assigneesMsg.value = r.data?.message || '退回失败'
    }
  } catch (e: any) {
    assigneesOk.value = false; assigneesMsg.value = e?.response?.data?.detail || '退回失败'
  } finally { assigneesSubmitting.value = false }
}

// 0901 办理人不可承接退回：指派说明作为原因（复用审批人退回的确认弹窗防误触模式）
const handlerRejectConfirm = ref(false)
const handlerRejectSubmitting = ref(false)

function askHandlerReject() {
  if (!approverNote.value.trim()) {
    approverOk.value = false
    approverMsg.value = '请先填写指派说明（退回时将作为不可承接原因提交）'
    return
  }
  handlerRejectConfirm.value = true
}

async function doHandlerReject() {
  if (!activeId.value || !approverNote.value.trim()) return
  handlerRejectSubmitting.value = true; approverMsg.value = ''
  try {
    const r = await handlerRejectApi(activeId.value, approverNote.value.trim())
    if (r.data?.success) {
      approverOk.value = true; approverMsg.value = r.data?.message || '已退回录入客服'
      handlerRejectConfirm.value = false
      approverNote.value = ''
      await reload()
    } else {
      approverOk.value = false; approverMsg.value = r.data?.message || '退回失败'
    }
  } catch (e: any) {
    approverOk.value = false; approverMsg.value = e?.response?.data?.detail || '退回失败'
  } finally { handlerRejectSubmitting.value = false }
}

// 0820 AI 分工建议（恢复 0819 删除的 AIDivisionSuggest 的 AI 部分，不做部门通知）
async function doAiDivision() {
  if (!complaint.value?.fault_phenomenon?.trim()) return
  divisionLoading.value = true; divisionMsg.value = ''
  try {
    const r = await diagnoseComplaint(
      complaint.value.fault_phenomenon.trim(),
      complaint.value.equipment_model?.trim() || '',
      complaint.value.customer_name || '',
    )
    if (r.data?.success && r.data.data) {
      const d = r.data.data
      divisionResult.value = d
      divisionOk.value = true; divisionMsg.value = 'AI 分工建议已生成，并已填入上方「承接可行性评估」（可修改）'
      // 自动填入评估（用户可改）
      assigneesForm.evaluation = `初步诊断：${d.preliminary_diagnosis}\n协同方案：${d.collaboration_workflow}`
      // 0902 采纳比对快照（提交指派时与最终评估比对匹配度）
      aiDivisionSuggest.value = { no: complaint.value?.complaint_no || '', text: assigneesForm.evaluation }
      // 记录 AI 建议文本（供操作完成后的评价卡片）
      aiSuggestion.current = `初步诊断：${d.preliminary_diagnosis}\n牵头工程师：${d.lead_engineer}\n参与工程师：${(d.participating_engineers || []).join('、')}\n协同方案：${d.collaboration_workflow}`
    }
  } catch (e: any) {
    console.error('ai division error:', e)
    divisionOk.value = false; divisionMsg.value = 'AI 服务暂不可用，请手动填写评估'
  } finally { divisionLoading.value = false }
}

// 0820 AI 排期建议（恢复 0819 删除的 AssignEngineer 的 AI 部分；ai_function 保持 'suggest_schedule' 以对接排期准确度看板）
function scheduleTargetName(): string {
  const users = selectedAssigneeUsers.value
  if (assigneesForm.primaryUserId) {
    const p = users.find(u => u.id === assigneesForm.primaryUserId)
    if (p) return p.display_name
  }
  if (assigneesForm.userIds.length === 1) {
    const u = users.find(x => x.id === assigneesForm.userIds[0])
    if (u) return u.display_name
  }
  return ''
}

async function doAiSchedule() {
  const target = scheduleTargetName()
  if (!target) { scheduleOk.value = false; scheduleMsg.value = '请先选择主要推进人（或仅选一位承接人）'; return }
  scheduleLoading.value = true; scheduleMsg.value = ''
  try {
    const r = await getScheduleSuggestion(target, complaint.value?.fault_category || '', assigneesForm.estimatedHours || 0, assigneesForm.userIds.length)
    if (r.data?.success && r.data.data) {
      const d = r.data.data
      scheduleResult.value = d
      scheduleOk.value = true; scheduleMsg.value = ''
      aiSuggestion.current = `AI 排期建议：${d.recommended_hours}h（${d.reasoning}）`
      // 0820 采纳记录移到「应用到预估工时」时再记（点击即记会虚增采纳率）
    }
  } catch (e: any) {
    console.error('ai schedule error:', e)
    scheduleOk.value = false; scheduleMsg.value = 'AI 服务暂不可用'
  } finally { scheduleLoading.value = false }
}

// 0821 一键同时生成分工与排期建议（按钮合并；先分工后排期，评价卡记录最终为排期建议）
async function doAiDivisionAndSchedule() {
  await doAiDivision()
  await doAiSchedule()
}

function applyScheduleHours() {
  if (scheduleResult.value) {
    assigneesForm.estimatedHours = scheduleResult.value.recommended_hours
    // 0820 真正应用建议工时才记录采纳（供排期准确度统计，ai_function 保持 'suggest_schedule'）
    import('@/api/eval').then(m => {
      m.recordAiAdoption(complaint.value?.complaint_no || '', 'suggest_schedule',
        String(scheduleResult.value!.recommended_hours), true, scheduleResult.value!.recommended_hours)
    }).catch(() => {})
  }
}

async function doAssignAssignees() {
  if (!activeId.value) return
  if (!assigneesForm.evaluation.trim()) { assigneesOk.value = false; assigneesMsg.value = '请填写承接可行性评估'; return }
  if (!assigneesForm.estimatedHours || assigneesForm.estimatedHours <= 0) { assigneesOk.value = false; assigneesMsg.value = '请填写预估工时'; return }
  if (!assigneesForm.userIds.length) { assigneesOk.value = false; assigneesMsg.value = '请选择承接人'; return }
  // 0820 主要推进人必选且必须在已选承接人中
  if (!assigneesForm.primaryUserId) { assigneesOk.value = false; assigneesMsg.value = '请指定一位主要推进人'; return }
  if (!assigneesForm.userIds.includes(assigneesForm.primaryUserId)) { assigneesOk.value = false; assigneesMsg.value = '主要推进人必须在已选承接人中'; return }
  assigneesSubmitting.value = true; assigneesMsg.value = ''
  try {
    const r = await assignAssigneesApi(activeId.value, {
      evaluation: assigneesForm.evaluation.trim(),
      estimated_hours: assigneesForm.estimatedHours,
      user_ids: assigneesForm.userIds,
      planned_start: assigneesForm.plannedStart || '',
      planned_end: assigneesForm.plannedEnd || '',
      force: assigneesForce.value,
      primary_user_id: assigneesForm.primaryUserId,
    })
    const data = r.data
    if (data?.success) {
      if (data.data?.has_conflict && !assigneesForce.value) {
        assigneesForce.value = true
        assigneesConflictMsg.value = data.data?.message || '存在处理中工单冲突，确认继续指派？'
        assigneesOk.value = false
      } else {
        assigneesOk.value = true; assigneesMsg.value = data?.message || '已指派承接人'
        assigneesConflictMsg.value = ''
        assigneesForce.value = false
        // 0902 AI 采纳：最终评估 vs AI 分工建议的匹配度（清空前比对；快照绑定单号防串单）
        const divisionSuggest = aiDivisionSuggest.value
        if (divisionSuggest && divisionSuggest.no === (complaint.value?.complaint_no || '')) {
          const sim = bigramDice(divisionSuggest.text, assigneesForm.evaluation.trim())
          import('@/api/eval').then(m => {
            m.recordAiAdoption(divisionSuggest.no, 'diagnose', divisionSuggest.text.slice(0, 500), sim >= AI_ADOPTION_MATCH_THRESHOLD, sim)
          }).catch(() => {})
        }
        aiDivisionSuggest.value = null
        Object.assign(assigneesForm, { evaluation: '', estimatedHours: 0, userIds: [], plannedStart: '', plannedEnd: '', primaryUserId: 0 })
        divisionResult.value = null; divisionMsg.value = ''
        scheduleResult.value = null; scheduleMsg.value = ''
        // 0820 指派完成弹出 assign 评价卡（提交后 onFeedbackDone 自动 reload 并跳下一单）
        onActionDone('assign')
      }
    } else {
      assigneesOk.value = false; assigneesMsg.value = data?.message || '指派失败'
    }
  } catch (e: any) {
    assigneesOk.value = false; assigneesMsg.value = e?.response?.data?.detail || '指派失败'
  } finally { assigneesSubmitting.value = false }
}

async function doCannotHandle() {
  if (!activeId.value || !cannotHandleReason.value.trim()) {
    cannotHandleOk.value = false; cannotHandleMsg.value = '请填写处理不了原因'; return
  }
  cannotHandleSubmitting.value = true; cannotHandleMsg.value = ''
  try {
    const r = await cannotHandleApi(activeId.value, cannotHandleReason.value.trim())
    if (r.data?.success) {
      cannotHandleOk.value = true; cannotHandleMsg.value = r.data?.message || '已回退指派审批人'
      cannotHandleReason.value = ''
      await reload()
    } else {
      cannotHandleOk.value = false; cannotHandleMsg.value = r.data?.message || '操作失败'
    }
  } catch (e: any) {
    cannotHandleOk.value = false; cannotHandleMsg.value = e?.response?.data?.detail || '操作失败'
  } finally { cannotHandleSubmitting.value = false }
}

async function doAddParticipants() {
  if (!activeId.value || !participantIds.value.length) {
    participantOk.value = false; participantMsg.value = '请选择参与人'; return
  }
  participantSubmitting.value = true; participantMsg.value = ''
  try {
    const r = await addParticipantsApi(activeId.value, participantIds.value)
    if (r.data?.success) {
      participantOk.value = true; participantMsg.value = r.data?.message || '已追加参与人'
      participantIds.value = []
      await reload()
    } else {
      participantOk.value = false; participantMsg.value = r.data?.message || '操作失败'
    }
  } catch (e: any) {
    participantOk.value = false; participantMsg.value = e?.response?.data?.detail || '操作失败'
  } finally { participantSubmitting.value = false }
}

// 0820 变更主要推进人（审批人/管理员，处理中）
async function doSetPrimary() {
  if (!activeId.value || !primaryChangeUserId.value) {
    primaryOk.value = false; primaryMsg.value = '请选择新的主要推进人'; return
  }
  primarySubmitting.value = true; primaryMsg.value = ''
  try {
    const r = await setPrimaryAssignee(activeId.value, primaryChangeUserId.value)
    if (r.data?.success) {
      primaryOk.value = true; primaryMsg.value = r.data?.message || '主要推进人已变更'
      primaryChangeUserId.value = 0
      await reload()
    } else {
      primaryOk.value = false; primaryMsg.value = r.data?.message || '操作失败'
    }
  } catch (e: any) {
    primaryOk.value = false; primaryMsg.value = e?.response?.data?.detail || '操作失败'
  } finally { primarySubmitting.value = false }
}

async function loadAttachments() {
  if (!activeId.value) return
  try {
    const r = await apiClient.get(`/api/complaints/${activeId.value}/attachments`)
    if (r.data?.success) attachments.value = r.data.data || []
  } catch { /* ignore */ }
}

// 0728 相似历史案例检索（v2.1 3_工单处理.py 330-388 行 两阶段：FTS5 秒出 + AI 方案推荐）
const similarCases = ref<any[]>([])
const similarLoading = ref(false)
const caseFeedbackMap = ref<Record<string, any>>({})

async function loadCaseFeedback() {
  if (!complaint.value?.complaint_no) return
  try {
    const r = await import('@/api/ai').then(m => m.getCaseFeedback(complaint.value!.complaint_no))
    if (r.data?.success) caseFeedbackMap.value = r.data.data || {}
  } catch (e) { console.error('case feedback load error:', e) }
}

async function loadSimilarCases() {
  if (!complaint.value?.fault_phenomenon) return
  similarLoading.value = true
  try {
    const r = await findSimilarCasesQuick(
      complaint.value.fault_phenomenon,
      complaint.value.fault_category || '',
    )
    if (r.data?.success) similarCases.value = r.data.data || []
  } catch (e: any) { console.error('similar cases error:', e) }
  finally { similarLoading.value = false }
}

// Checklist
const checklistItems = ref<string[]>([])
const checklistChecked = ref<boolean[]>([])
const checklistLoading = ref(false)

async function loadChecklist() {
  if (!complaint.value?.fault_category) return
  checklistLoading.value = true
  try {
    const r = await getChecklist(complaint.value.fault_category)
    if (r.data?.success) {
      checklistItems.value = r.data.data || []
      checklistChecked.value = r.data.data?.map(() => false) || []
    }
  } catch (e: any) { console.error('checklist error:', e) }
  finally { checklistLoading.value = false }
}

// AI 方案推荐（LLM 重排，手动触发）
const aiSolutionLoading = ref(false)
const aiSolutionResult = ref<any>(null)

async function doAiSolution() {
  if (!complaint.value) return
  aiSolutionLoading.value = true
  try {
    const r = await searchSimilarCases(
      complaint.value.fault_phenomenon,
      complaint.value.equipment_model || '',
      complaint.value.fault_category || '',
    )
    if (r.data?.success) {
      aiSolutionResult.value = r.data.data
      // 0730 记录 AI 方案文本
      aiSuggestion.current = r.data.data?.summary || ''
    }
  } catch (e: any) { console.error('ai solution error:', e) }
  finally { aiSolutionLoading.value = false }
}

// 0807 解析关联工单列表（JSON 数组 -> [{id, no}]）
const linkedComplaints = computed(() => {
  try {
    const raw = complaint.value?.linked_complaint_ids
    if (!raw || raw === '[]') return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed as Array<{id: number, no: string}>
  } catch { return [] }
})

// 0915 关联工单折叠 + 弹窗表格：内联只显示前 N 个，弹窗批量拉概要（编号/设备/优先级/状态/问题/解决方案）
const LINKED_INLINE_LIMIT = 3
const showLinkedModal = ref(false)
const linkedRows = ref<ComplaintBrief[]>([])
const linkedDeleted = ref<Array<{id: number, no: string}>>([])
const linkedLoading = ref(false)
const linkedError = ref('')

async function openLinkedModal() {
  showLinkedModal.value = true
  if (!linkedComplaints.value.length) return
  linkedLoading.value = true
  linkedError.value = ''
  try {
    const r = await getComplaintBriefsByIds(linkedComplaints.value.map(lc => lc.id))
    if (r.data?.success && r.data.data) {
      const found = new Set(r.data.data.map(b => b.id))
      linkedRows.value = r.data.data
      linkedDeleted.value = linkedComplaints.value.filter(lc => !found.has(lc.id))
    } else {
      linkedRows.value = []
      linkedDeleted.value = []
      linkedError.value = r.data?.message || '加载关联工单失败'
    }
  } catch {
    linkedRows.value = []
    linkedDeleted.value = []
    linkedError.value = '加载关联工单失败，请重试'
  } finally {
    linkedLoading.value = false
  }
}

function goLinkedDetail(id: number) {
  showLinkedModal.value = false
  router.push(`/work-order/${id}`)
}

const statusNorm = computed(() => complaint.value?.status || '')

const imgAtts = computed(() => attachments.value.filter(a => (a.mime_type || '').startsWith('image/')))
const docAtts = computed(() => attachments.value.filter(a => !(a.mime_type || '').startsWith('image/')))

function onSearch() {
  const kw = searchKeyword.value.toLowerCase()
  filteredOptions.value = options.value.filter(o =>
    !kw || o.complaint_no.toLowerCase().includes(kw) ||
    o.customer_name.toLowerCase().includes(kw) ||
    (o.fault_category || '').toLowerCase().includes(kw) ||
    (o.equipment_sn || '').toLowerCase().includes(kw) ||
    (o.status || '').toLowerCase().includes(kw)
  )
}

// 0826 分组折叠：两组默认展开（可手动收起）；搜索时强制展开，避免命中项被藏在折叠组里
const groupCollapsed = reactive<Record<string, boolean>>({ required: false, optional: false })
function toggleGroup(key: string) { groupCollapsed[key] = !groupCollapsed[key] }
function isGroupCollapsed(key: string) {
  if (searchKeyword.value.trim()) return false
  return groupCollapsed[key]
}

// 0826 侧栏分组：需我处理（此单我有分内必做动作）/ 按需关注（处理中我仅审批跟进、终态、无关单）。
// 口径：处理中→我承接/推进才必做（仅审批=按需）；指派审批人列是办理人工作队列；
// 其余非终态单出现即与我相关（录入/审批绑定）→ 必做；管理员全量视角无分内必做。
const sidebarGroups = computed(() => {
  const required: typeof filteredOptions.value = []
  const optional: typeof filteredOptions.value = []
  for (const o of filteredOptions.value) {
    const st = o._status || o.status
    const mine = o._my_roles || []
    let isReq: boolean
    if (st === '已关闭' || st === '已撤回') isReq = false
    else if (st === '处理中') isReq = mine.includes('assignee') || mine.includes('primary')
    else if (role.value === '管理员') isReq = false
    else if (st === '指派审批人') isReq = role.value === '办理人' || mine.length > 0
    else isReq = mine.length > 0
    ;(isReq ? required : optional).push(o)
  }
  return [
    { key: 'required', title: '需我处理', hint: '', items: required },
    {
      key: 'optional',
      title: myOrdersOnly.value ? '按需关注' : '其他工单',
      hint: (myOrdersOnly.value && (role.value === '审批人' || role.value === '办理人'))
        ? '处理中您仅跟进；追加参与人 / 变更推进人按需操作' : '',
      items: optional,
    },
  ]
})

async function loadList() {
  listLoading.value = true; listError.value = ''
  try {
    // 0730 传 myOrdersOnly 给后端，支持姓名匹配
    // 0826 移除 approver_group 参数：审批人分组过滤改为前端按 _my_roles 平铺分组
    const params: Record<string, any> = {}
    if (myOrdersOnly.value) params.my_orders_only = true
    const r = await apiClient.get('/api/complaints/sidebar/tasks', { params })
    if (r.data?.success) {
      const data = r.data.data
      // options 是角色应看到的相关工单列表
      const raw = (data.options || [])
      options.value = raw.map((c: any) => ({
        id: c.id, complaint_no: c.complaint_no,
        customer_name: c.customer_name, status: c.status,
        fault_category: c.fault_category || '',
        equipment_sn: c.equipment_sn || '',  // 0914 支持按设备编号搜索（后端本就返回该字段）
        // 0804 携带排序所需字段
        _planned_end_time: c.planned_end_time || '',
        _expected_complete_date: c.expected_complete_date || '',
        _status: c.status || '',
        // 0826 我的身份标记（后端挂载），供 sidebarGroups 分组
        _my_roles: c._my_roles || [],
      }))
      // 0804 排序：处理中按计划结束时间，待客户确认按客户期望时间
      options.value.sort((a, b) => {
        const sa = a._status
        const sb = b._status
        // 处理中排最前，组内按 planned_end_time 升序
        if (sa === '处理中' && sb !== '处理中') return -1
        if (sa !== '处理中' && sb === '处理中') return 1
        if (sa === '处理中' && sb === '处理中') {
          const aT = a._planned_end_time, bT = b._planned_end_time
          if (!aT && !bT) return 0
          if (!aT) return 1
          if (!bT) return -1
          return aT.localeCompare(bT)
        }
        // 待客户确认次之，组内按 expected_complete_date 升序
        if (sa === '待客户确认' && sb !== '待客户确认') return -1
        if (sa !== '待客户确认' && sb === '待客户确认') return 1
        if (sa === '待客户确认' && sb === '待客户确认') {
          const aT = a._expected_complete_date, bT = b._expected_complete_date
          if (!aT && !bT) return 0
          if (!aT) return 1
          if (!bT) return -1
          return aT.localeCompare(bT)
        }
        return 0
      })
      onSearch()
    } else {
      listError.value = r.data?.message || '加载失败'
    }
  } catch (e: any) {
    listError.value = e?.response?.data?.detail || e?.message || '网络请求失败'
    console.error('loadList error:', e)
  } finally { listLoading.value = false }
}

async function loadComplaint(id: number) {
  detailLoading.value = true
  // 0820 操作计时起点（此前 __detailStart 从未被设置，ticket_resolve 计时恒不产生）
  ;(window as any).__detailStart = Date.now()
  // ── Step 1: 加载工单主体 ──
  try {
    const r = await apiClient.get(`/api/complaints/${id}`)
    if (r.data?.success) {
      complaint.value = r.data.data
    }
  } catch (e: any) {
    console.error('loadComplaint error:', e)
    complaint.value = null
    detailLoading.value = false
    return  // 主体加载失败则终止，不继续加载附属数据
  }

  // ── Step 2: 加载进度信息（附属数据，失败不影响主体展示）──
  try {
    const pr = await apiClient.get(`/api/complaints/${id}/progress-info`)
    if (pr.data?.success) {
      const d = pr.data.data
      progressInfo.pct = d.pct
      progressInfo.method = d.method
      progressInfo.latest = d.latest
      progressHistory.value = d.history || []
    }
  } catch (e: any) {
    console.warn('loadProgressInfo error (non-fatal):', e?.message)
  }

  // ── Step 2b: 0803 加载统一工单时间线（失败不影响主体展示）──
  try {
    const tl = await apiClient.get(`/api/complaints/${id}/timeline`)
    if (tl.data?.success) {
      timelineLogs.value = tl.data.data.logs || []
    }
  } catch (e: any) {
    console.warn('loadTimeline error (non-fatal):', e?.message)
  }

  // ── Step 3: 附属信息 ──
  if (complaint.value) {
    const hours = (complaint.value as any)._processing_hours
    if (hours) processingHours.value = hours
  }
  // 静默加载附件（失败不影响主流程）
  await loadAttachments()
  // 自动 FTS5 相似案例 + Checklist（v2.1 3_工单处理.py 330-348 行）
  loadSimilarCases()
  loadChecklist()
  // 0805 加载案例检索评价
  loadCaseFeedback()
  detailLoading.value = false
}

// 0914 切换工单时清空上一单残留（AI 结果/相似案例/清单/各操作表单与提示），
// 仅在真正换单的路径调用（selectComplaint / 路由 id 变化）；同单 reload / WebSocket 刷新不调，
// 避免清掉用户正在填写的内容
function resetPerComplaintState() {
  // 0915 关联工单弹窗随工单切换关闭，残留数据下次打开重拉
  showLinkedModal.value = false
  linkedRows.value = []
  linkedDeleted.value = []
  linkedError.value = ''
  // AI 智能辅助面板：方案推荐结果、相似案例、排查清单、评价映射、分工/排期建议
  aiSolutionResult.value = null
  similarCases.value = []
  caseFeedbackMap.value = {}
  checklistItems.value = []
  checklistChecked.value = []
  divisionResult.value = null
  divisionMsg.value = ''; divisionOk.value = false
  scheduleResult.value = null
  scheduleMsg.value = ''; scheduleOk.value = false
  intakeSelfCheckLoading.value = false
  intakeSelfCheckSuccess.value = false
  aiSuggestion.current = ''
  // 操作区表单残留（上一单填写的评估/说明/原因等不再串到新工单）
  Object.assign(intakeForm, { priority: '', route: '', evaluation: '' })
  intakeMsg.value = ''; intakeOk.value = false
  resubmitMsg.value = ''; resubmitOk.value = false
  investigationRemark.value = ''; investigationMsg.value = ''; investigationOk.value = false
  approverUserId.value = 0; approverNote.value = ''
  approverMsg.value = ''; approverOk.value = false
  Object.assign(assigneesForm, {
    evaluation: '', estimatedHours: 0, userIds: [],
    plannedStart: '', plannedEnd: '', primaryUserId: 0,
  })
  assigneesConflictMsg.value = ''; assigneesMsg.value = ''; assigneesOk.value = false
  cannotHandleReason.value = ''; cannotHandleMsg.value = ''; cannotHandleOk.value = false
  participantIds.value = []; participantMsg.value = ''; participantOk.value = false
  primaryChangeUserId.value = 0; primaryMsg.value = ''; primaryOk.value = false
  emailReviewMsg.value = ''; emailReviewOk.value = false
  emailRejectMode.value = false; emailRejectNote.value = ''
  // 评价卡片与操作区冻结状态
  awaitingFeedback.value = false
  feedbackTarget.value = { complaintNo: '', feedbackType: '' }
}

async function selectComplaint(id: number) {
  // 切换工单时清空上一单残留（评价卡片/AI 结果/操作表单），防止内容串到新工单
  resetPerComplaintState()
  activeId.value = id
  // 同步更新 URL，使刷新后能恢复选中状态
  if (route.params.id !== String(id)) {
    // 0819 移动端用 push（系统返回键可回列表），桌面保持 replace（历史不膨胀）
    if (isMobileView()) router.push(`/work-order/${id}`)
    else router.replace(`/work-order/${id}`)
  }
  await loadComplaint(id)
}

async function reload() {
  if (activeId.value) {
    reloadingGate.value = true
    await loadComplaint(activeId.value)
    await loadList()
    checkPendingFeedback()
    // 300ms 后解除锁定，允许 WebSocket 再次触发刷新
    setTimeout(() => { reloadingGate.value = false }, 300)
  }
}

// 0731 评价操作完成：冻结操作区 + 显示卡片 + 滚动；不 reload，保持旧状态页面
async function onActionDone(feedbackType: string) {
  // 0805 操作计时：工单处理（resolve 操作）
  if (feedbackType === 'resolve' && (window as any).__detailStart) {
    const duration = Date.now() - (window as any).__detailStart
    import('@/api/eval').then(m => {
      m.recordActivity('/work-order', 'timing', { action_name: 'ticket_resolve', duration_ms: duration, complaint_id: complaint.value?.id || 0 })
    }).catch(() => {})
  }
  if (complaint.value?.complaint_no) {
    awaitingFeedback.value = true  // 冻结操作区
    feedbackTarget.value = {
      complaintNo: complaint.value.complaint_no,
      feedbackType,
    }
    // 滚动到评价卡片
    nextTick(() => {
      const el = document.getElementById('ai-feedback-card')
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
    // 不调用 reload：保持旧状态的工单数据，操作区被 awaitingFeedback 冻结，只显示评价卡片
  }
}

// 0731 用户主动操作（提交评价/关闭卡片）→ 解冻操作区 + 隐藏卡片 + reload 刷新到新状态
// 0804 reload 完成后自动跳转到下一个待处理工单
async function onFeedbackDone() {
  awaitingFeedback.value = false  // 解冻操作区
  feedbackTarget.value = { complaintNo: '', feedbackType: '' }
  aiSuggestion.current = ''  // 0820 评价提交后清空，防止文本串到下一个工单
  await reload()  // 刷新工单数据到新状态
  // reload 完成后，当前工单状态已变更（可能已完成/关闭/拒收），自动跳转到下一个待处理工单
  const next = filteredOptions.value.find(o => o.id !== activeId.value)
  if (next) {
    selectComplaint(next.id)
  }
}

// 0729 在详情页直接确认优先级

// 0731 WebSocket 实时刷新：其他用户操作工单时自动更新侧边栏列表；若恰好是当前工单则同时刷新详情
// 评价卡片显示期间跳过详情刷新（awaitingFeedback），避免打断用户评价
const offWsDetail = onWsEvent((evt) => {
  if (evt.type === 'complaint_created' || evt.type === 'complaint_updated' || evt.type === 'complaint_deleted') {
    // 0803 手动操作正在 reload 时跳过 WebSocket 刷新，防止双重渲染闪烁
    if (reloadingGate.value) return
    loadList()
    if (!awaitingFeedback.value && activeId.value && evt.complaint_id === activeId.value) {
      loadComplaint(activeId.value)
    }
  }
})

let pendingFeedbackCount = 0

async function checkPendingFeedback() {
  if (!complaint.value?.complaint_no || !auth.role) return
  try {
    const r = await getPendingFeedback(complaint.value.complaint_no)
    if (r.data?.success) {
      pendingFeedbackCount = r.data.data?.count || 0
    }
  } catch { /* 静默 */ }
}


function onVisibilityChange() {
  if (document.visibilityState === 'visible') {
    loadList()
  }
}

onMounted(async () => {
  // 0820 首载加载列表 + 注册 visibilitychange（此前 onUnmounted 移除的监听从未被添加，首屏列表为空）
  await loadList()
  document.addEventListener('visibilitychange', onVisibilityChange)
  // 0820 桌面端无 URL 参数时自动选中第一个工单（移动端保持列表优先，用户决策）
  if (!route.params.id && !isMobileView() && filteredOptions.value.length) {
    selectComplaint(filteredOptions.value[0].id)
  }
})

onUnmounted(() => {
  offWsDetail()
  document.removeEventListener('visibilitychange', onVisibilityChange)
})

// Watch route changes (navigating from kanban, or router.replace in selectComplaint)
// 0820 加 immediate：直接进入 /work-order/:id（如看板跳转）时初始路由立即加载详情（此前需 URL 变化才触发）
watch(() => route.params.id, async (newId, oldId) => {
  if (newId) {
    const id = Number(newId)
    // 避免与 selectComplaint 中的主动调用重复
    if (!isNaN(id) && id !== activeId.value) {
      // 外部导航切换工单时同样清空上一单残留（评价卡片/AI 结果/操作表单）
      resetPerComplaintState()
          activeId.value = id
      await loadComplaint(id)
    }
  }
}, { immediate: true })
</script>
