<!-- 0727 Phase 4 系统管理 — 用户列表/新增/编辑/密码管理/停用（管理员专属）
     来源：pages/6_系统管理.py（v2.1 Streamlit）-->
<template>
  <AppLayout>
    <div class="p-6 space-y-4">
      <div>
        <h1 class="text-2xl font-bold">⚙️ 系统管理</h1>
        <p class="text-sm text-gray-500 mt-1">用户账号管理 · 角色与部门配置 · 知识库管理 · 工单快速管理</p>
      </div>

      <!-- Tab 切换 -->
      <div class="flex gap-1 bg-gray-100 rounded-lg p-1 w-fit">
        <button
          v-for="tab in tabs" :key="tab.key"
          @click="activeTab = tab.key"
          :class="['px-4 py-1.5 rounded-md text-sm font-medium transition',
            activeTab === tab.key ? 'bg-white shadow text-primary' : 'text-gray-500 hover:text-gray-700']"
        >{{ tab.label }}</button>
      </div>

      <!-- ========== Tab 1：用户列表 ========== -->
      <template v-if="activeTab === 'list'">
        <!-- 筛选栏 -->
        <div class="bg-white rounded-lg border border-gray-200 p-4 flex flex-wrap items-end gap-3">
          <div>
            <label class="text-xs text-gray-500 mb-1 block">按角色筛选</label>
            <select v-model="roleFilter" @change="fetchUsers"
              class="px-3 py-1.5 border border-gray-300 rounded text-sm">
              <option value="">全部</option>
              <option v-for="r in meta.roles" :key="r" :value="r">{{ r }}</option>
            </select>
          </div>
          <label class="flex items-center gap-1.5 text-sm text-gray-600 pb-1.5 cursor-pointer">
            <input type="checkbox" v-model="showInactive" @change="fetchUsers" class="rounded" />
            显示已停用账号
          </label>
          <button @click="fetchUsers" class="px-3 py-1.5 border border-gray-300 rounded text-sm hover:bg-gray-50 transition">
            🔄 刷新
          </button>
        </div>

        <p class="text-xs text-gray-500">
          {{ showInactive ? `共 ${users.length} 名用户（活跃 ${activeCount}）` : `共 ${users.length} 名活跃用户` }}
        </p>

        <!-- 用户卡片列表 — 0727 角色彩徽 + 简洁布局 -->
        <div v-if="loading" class="text-center text-gray-400 py-12">加载中...</div>
        <div v-else-if="!users.length" class="text-center text-gray-400 py-12">暂无匹配用户</div>
        <div v-else class="space-y-2">
          <div v-for="u in users" :key="u.id"
            class="bg-white rounded-lg border border-gray-200 p-3.5 flex items-center gap-3"
            :class="{ 'opacity-60': !u.is_active }">
            <!-- 头像 -->
            <div class="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-xs font-bold text-indigo-600 shrink-0 select-none">
              {{ (u.display_name || u.username)[0] }}
            </div>
            <!-- 名称 + 账号 -->
            <div class="w-36 shrink-0 min-w-0">
              <div class="font-medium text-sm flex items-center gap-1 truncate">
                {{ u.display_name }}
                <span v-if="!u.is_active" class="text-xs text-red-500 shrink-0">🔴</span>
              </div>
              <div class="text-xs text-gray-400 truncate">{{ u.username }}</div>
            </div>
            <!-- 0819 角色彩徽 -->
            <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-medium shrink-0"
              :class="ROLE_COLORS[u.role] || 'bg-gray-100 text-gray-600'">
              {{ u.role }}
            </span>
            <!-- 职位 -->
            <span class="text-xs text-gray-500 flex-1 min-w-0 truncate">💼 {{ u.position || '—' }}</span>
            <!-- 创建时间 -->
            <span class="text-xs text-gray-400 shrink-0 tnum">📅 {{ (u.created_at || '').slice(0, 10) }}</span>
            <!-- 编辑 -->
            <button @click="openEdit(u)" title="编辑用户"
              class="px-3 py-1.5 border border-gray-300 rounded text-sm hover:bg-gray-50 hover:border-gray-400 transition shrink-0">
              ✏️ 编辑
            </button>
          </div>
        </div>
      </template>

      <!-- ========== Tab 2：新增用户 ========== -->
      <template v-if="activeTab === 'create'">
        <div class="bg-white rounded-lg border border-gray-200 p-6 max-w-2xl">
          <h3 class="font-semibold mb-4">➕ 新增用户账号</h3>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label class="text-xs text-gray-500 mb-1 block">账号 *</label>
              <input v-model="createForm.username" placeholder="如：sw_eng_2"
                class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm" />
            </div>
            <div>
              <label class="text-xs text-gray-500 mb-1 block">显示名/姓名 *</label>
              <input v-model="createForm.display_name" placeholder="如：软件工程师2"
                class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm" />
            </div>
            <div>
              <label class="text-xs text-gray-500 mb-1 block">密码 *（至少 4 位）</label>
              <input v-model="createForm.password" type="password" placeholder="至少4位"
                class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm" />
            </div>
            <div>
              <label class="text-xs text-gray-500 mb-1 block">确认密码 *</label>
              <input v-model="createForm.passwordConfirm" type="password"
                class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm" />
            </div>
            <!-- 0819 角色下拉 + 职位 -->
            <div>
              <label class="text-xs text-gray-500 mb-1 block">角色 *</label>
              <select v-model="createForm.role"
                class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm">
                <option value="">请选择角色</option>
                <option v-for="r in meta.roles" :key="r" :value="r">{{ r }}</option>
              </select>
            </div>
            <div>
              <label class="text-xs text-gray-500 mb-1 block">公司职位 *（手填）</label>
              <input v-model="createForm.position" placeholder="如：高级机械工程师 / 客服专员"
                class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm" />
            </div>
            <!-- 0824 钉钉绑定（选填） -->
            <div>
              <label class="text-xs text-gray-500 mb-1 block">钉钉UserID（选填）</label>
              <input v-model="createForm.dingtalk_userid" placeholder="钉钉管理后台-通讯录中的UserID"
                class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm" />
            </div>
          </div>
          <button @click="doCreate" :disabled="creating"
            class="mt-5 w-full px-4 py-2 bg-primary text-white rounded text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition">
            {{ creating ? '创建中...' : '✅ 创建账号' }}
          </button>
          <div v-if="createMsg" :class="['text-xs mt-2', createOk ? 'text-green-600' : 'text-red-500']">{{ createMsg }}</div>
        </div>
      </template>

      <!-- ========== Tab 3：离职交接（1009 新增） ========== -->
      <template v-if="activeTab === 'handover'">
        <div class="bg-white rounded-lg border border-gray-200 p-6 max-w-2xl">
          <h3 class="font-semibold mb-1">🔄 离职交接</h3>
          <p class="text-xs text-gray-500 mb-4">
            把离职人员名下的工单（审批人/承接人指派 + 录入客服归属）移交给接收人。
            历史过程记录完整保留在各工单时间线，交接动作本身也会逐单留痕。
          </p>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label class="text-xs text-gray-500 mb-1 block">离职人员 *</label>
              <select v-model="handoverFrom" @change="onHandoverChange"
                class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm">
                <option value="">请选择（含已停用账号）</option>
                <option v-for="u in handoverCandidates" :key="u.id" :value="u.id">
                  {{ u.display_name }}（{{ u.role }}）{{ u.is_active ? '' : ' · 已停用' }}
                </option>
              </select>
            </div>
            <div>
              <label class="text-xs text-gray-500 mb-1 block">接收人 *</label>
              <select v-model="handoverTo" @change="onHandoverChange"
                class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm">
                <option value="">请选择（在职账号）</option>
                <option v-for="u in handoverReceivers" :key="u.id" :value="u.id">
                  {{ u.display_name }}（{{ u.role }}）
                </option>
              </select>
            </div>
          </div>

          <!-- 预览统计 -->
          <div v-if="handoverPreview" class="mt-4 bg-gray-50 border border-gray-200 rounded p-3.5">
            <div class="text-sm font-medium mb-1.5">
              将移交 <span class="text-primary font-semibold text-base">{{ handoverPreview.total_complaints }}</span> 客户工程师单
              <span class="text-xs text-gray-400 ml-1">
                {{ handoverPreview.from_user.display_name }} → {{ handoverPreview.to_user.display_name }}
              </span>
            </div>
            <div class="text-xs text-gray-500 space-y-0.5">
              <div>· 作为审批人：{{ handoverPreview.as_approver }} 张（指派换绑）</div>
              <div>· 作为承接人：{{ handoverPreview.as_assignee }} 张（含主要推进人身份一并转移）</div>
              <div>· 作为录入客服：{{ handoverPreview.as_creator }} 张（「我的工单」归属与后续通知一并转移）</div>
            </div>
            <label v-if="fromUserIsActive" class="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer mt-2.5">
              <input type="checkbox" v-model="handoverDeactivate" class="rounded" />
              交接完成后停用该账号（软删除，数据保留）
            </label>
          </div>
          <div v-else-if="handoverPreviewLoading" class="text-xs text-gray-400 mt-3">统计中...</div>
          <p v-else-if="!handoverMsg" class="text-xs text-gray-400 mt-3">选择交接双方后自动统计待移交工单。</p>

          <button @click="confirmHandover" :disabled="!handoverPreview || handoverSubmitting"
            class="mt-5 w-full px-4 py-2 bg-primary text-white rounded text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition">
            🔄 {{ handoverSubmitting ? '交接中...' : '开始交接' }}
          </button>
          <div v-if="handoverMsg" :class="['text-xs mt-2', handoverOk ? 'text-green-600' : 'text-red-500']">{{ handoverMsg }}</div>
        </div>
      </template>

      <!-- ========== Tab 4：知识库管理（0729 新增） ========== -->
      <template v-if="activeTab === 'kb'">
        <KBManager />
      </template>

      <!-- ========== Tab 5：工单管理（0729 新增） ========== -->
      <template v-if="activeTab === 'complaints'">
        <ComplaintTable />
      </template>

      <!-- ========== Tab 6：邮箱设置（0811 新增） ========== -->
      <template v-if="activeTab === 'email'">
        <div class="bg-white rounded-lg border border-gray-200 p-6 max-w-2xl">
          <h3 class="font-semibold mb-1">📧 SMTP 邮箱设置</h3>
          <p class="text-xs text-gray-500 mb-4">
            配置后即可发送邮件通知（如待客户确认邮件）。修改即时生效，无需重启。
            <span v-if="smtpConfig.is_configured" class="text-green-600 ml-2">● 已配置</span>
            <span v-else class="text-gray-400 ml-2">● 未配置</span>
          </p>

          <div v-if="smtpLoading" class="text-center text-gray-400 py-8">加载中...</div>
          <template v-else>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label class="text-xs text-gray-500 mb-1 block">SMTP 服务器地址 *</label>
                <input v-model="smtpForm.smtp_host" placeholder="如：smtp.qiye.aliyun.com"
                  class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm" />
              </div>
              <div>
                <label class="text-xs text-gray-500 mb-1 block">端口</label>
                <input v-model.number="smtpForm.smtp_port" type="number" placeholder="587"
                  class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm" />
              </div>
              <div>
                <label class="text-xs text-gray-500 mb-1 block">用户名/账号 *</label>
                <input v-model="smtpForm.smtp_user" placeholder="如：noreply@company.com"
                  class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm" />
              </div>
              <div>
                <label class="text-xs text-gray-500 mb-1 block">密码 *</label>
                <div class="relative">
                  <input :type="showSmtpPassword ? 'text' : 'password'" v-model="smtpForm.smtp_password"
                    placeholder="输入 SMTP 授权码或密码"
                    class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm pr-8" />
                  <button @click="showSmtpPassword = !showSmtpPassword"
                    class="absolute right-1.5 top-1/2 -translate-y-1/2 text-xs text-gray-400 hover:text-gray-600"
                    type="button">{{ showSmtpPassword ? '🙈' : '👁' }}</button>
                </div>
              </div>
              <div class="md:col-span-2">
                <label class="text-xs text-gray-500 mb-1 block">发件人地址 *</label>
                <input v-model="smtpForm.smtp_from" placeholder="如：noreply@company.com"
                  class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm" />
              </div>
            </div>

            <!-- 操作按钮 -->
            <div class="flex gap-3 mt-5">
              <button @click="doTestSmtp" :disabled="smtpTesting"
                class="px-4 py-2 border border-gray-300 rounded text-sm hover:bg-gray-50 disabled:opacity-50 transition">
                {{ smtpTesting ? '🔄 测试中...' : '🔍 测试连接' }}
              </button>
              <button @click="doSaveSmtp" :disabled="smtpSaving"
                class="px-4 py-2 bg-primary text-white rounded text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition">
                💾 {{ smtpSaving ? '保存中...' : '保存设置' }}
              </button>
            </div>
            <div v-if="smtpMsg" :class="['text-xs mt-3', smtpOk ? 'text-green-600' : 'text-red-500']">{{ smtpMsg }}</div>
          </template>
        </div>
      </template>

      <!-- ========== Tab 7：钉钉通知设置（0824 新增） ========== -->
      <template v-if="activeTab === 'dingtalk'">
        <div class="bg-white rounded-lg border border-gray-200 p-6 max-w-2xl">
          <h3 class="font-semibold mb-1">📱 钉钉通知设置</h3>
          <p class="text-xs text-gray-500 mb-4">
            配置钉钉企业内部应用后，「待处理」类通知将同时推送到绑定用户的钉钉
            （action_card 卡片带【立即处理】按钮直达工单）。修改即时生效，无需重启。
            <span v-if="dingtalkConfig.is_configured" class="text-green-600 ml-2">● 已配置</span>
            <span v-else class="text-gray-400 ml-2">● 未配置</span>
          </p>

          <div v-if="dingtalkLoading" class="text-center text-gray-400 py-8">加载中...</div>
          <template v-else>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label class="text-xs text-gray-500 mb-1 block">AppKey *</label>
                <input v-model="dingtalkForm.app_key" placeholder="企业内部应用的 AppKey"
                  class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm" />
              </div>
              <div>
                <label class="text-xs text-gray-500 mb-1 block">AppSecret *</label>
                <div class="relative">
                  <input :type="showDingtalkSecret ? 'text' : 'password'" v-model="dingtalkForm.app_secret"
                    placeholder="输入应用密钥（留空=保留原值）"
                    class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm pr-8" />
                  <button @click="showDingtalkSecret = !showDingtalkSecret"
                    class="absolute right-1.5 top-1/2 -translate-y-1/2 text-xs text-gray-400 hover:text-gray-600"
                    type="button">{{ showDingtalkSecret ? '🙈' : '👁' }}</button>
                </div>
              </div>
              <div>
                <label class="text-xs text-gray-500 mb-1 block">AgentId *</label>
                <input v-model="dingtalkForm.agent_id" placeholder="如：123456789"
                  class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm" />
              </div>
              <div>
                <label class="text-xs text-gray-500 mb-1 block">系统访问地址 *（卡片跳转前缀）</label>
                <input v-model="dingtalkForm.public_base_url" placeholder="如：http://192.168.1.10:8506（不含末尾斜杠）"
                  class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm" />
              </div>
              <label class="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer">
                <input type="checkbox" v-model="dingtalkForm.enabled" class="rounded" />
                启用钉钉通知
              </label>
              <label class="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer">
                <input type="checkbox" v-model="dingtalkForm.dry_run" class="rounded" />
                调试模式（不真实发送，仅记录日志）
              </label>
            </div>

            <!-- 操作按钮 -->
            <div class="flex gap-3 mt-5">
              <button @click="doTestDingtalk" :disabled="dingtalkTesting"
                class="px-4 py-2 border border-gray-300 rounded text-sm hover:bg-gray-50 disabled:opacity-50 transition">
                {{ dingtalkTesting ? '🔄 测试中...' : '🔍 测试凭证' }}
              </button>
              <button @click="doSaveDingtalk" :disabled="dingtalkSaving"
                class="px-4 py-2 bg-primary text-white rounded text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition">
                💾 {{ dingtalkSaving ? '保存中...' : '保存设置' }}
              </button>
            </div>
            <div v-if="dingtalkMsg" :class="['text-xs mt-3', dingtalkOk ? 'text-green-600' : 'text-red-500']">{{ dingtalkMsg }}</div>

            <!-- 0825 手机号查 UserID 小工具（绑定用户辅助） -->
            <div class="mt-5 pt-4 border-t border-gray-100">
              <label class="text-xs font-medium text-gray-600 mb-2 block">🔎 通过手机号查钉钉 UserID（绑定用户用）</label>
              <div class="flex gap-2">
                <input v-model="useridLookup.mobile" placeholder="输入该员工钉钉绑定的手机号（11位）" maxlength="11"
                  class="flex-1 px-3 py-1.5 border border-gray-300 rounded text-sm" @keyup.enter="doLookupUserid" />
                <button @click="doLookupUserid" :disabled="useridLookup.loading"
                  class="px-4 py-1.5 border border-gray-300 rounded text-sm hover:bg-gray-50 disabled:opacity-50 transition whitespace-nowrap">
                  {{ useridLookup.loading ? '🔄 查询中...' : '🔍 查询' }}
                </button>
              </div>
              <div v-if="useridLookup.msg" :class="['text-xs mt-2', useridLookup.ok ? 'text-green-600' : 'text-red-500']">
                {{ useridLookup.msg }}
              </div>
              <div v-if="useridLookup.userid" class="text-xs mt-1.5 flex items-center gap-2 flex-wrap">
                <span class="mono">UserID：{{ useridLookup.userid }}</span>
                <span v-if="useridLookup.name" class="text-gray-500">（{{ useridLookup.name }}）</span>
                <button @click="copyUserid" type="button"
                  class="underline text-primary hover:text-primary/80">📋 复制</button>
              </div>
              <p class="text-xs text-gray-400 mt-2">
                前提：应用已开通「通讯录-个人信息」读权限；凭证用当前表单值（AppSecret 留空则用已保存值）。
              </p>
            </div>

            <p class="text-xs text-gray-400 mt-4">
              前提：钉钉管理后台创建企业内部应用并开通工作通知权限；用户绑定 = 在「用户列表」编辑中填写
              钉钉 UserID（可用上方工具按手机号查询，或钉钉管理后台-通讯录查看）。仅「待处理」类通知会推送。
            </p>
          </template>
        </div>
      </template>
    </div>

    <!-- ========== 编辑用户弹窗 ========== -->
    <Teleport to="body">
      <div v-if="editTarget" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-black/40" @click="editTarget = null"></div>
        <div class="relative bg-white rounded-lg shadow-xl p-6 w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
          <h3 class="text-lg font-semibold mb-4">编辑：{{ editTarget.display_name }}</h3>

          <div class="space-y-3">
            <div>
              <label class="text-xs text-gray-500 mb-1 block">显示名</label>
              <input v-model="editForm.display_name"
                class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm" />
            </div>
            <!-- 0819 角色 + 职位 -->
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="text-xs text-gray-500 mb-1 block">角色</label>
                <select v-model="editForm.role"
                  class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm">
                  <option v-for="r in meta.roles" :key="r" :value="r">{{ r }}</option>
                </select>
              </div>
              <div>
                <label class="text-xs text-gray-500 mb-1 block">公司职位</label>
                <input v-model="editForm.position"
                  class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm" />
              </div>
            </div>
            <!-- 0824 钉钉绑定 -->
            <div>
              <label class="text-xs text-gray-500 mb-1 block">钉钉UserID（空=不接收钉钉通知）</label>
              <input v-model="editForm.dingtalk_userid" placeholder="钉钉管理后台-通讯录中的UserID"
                class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm" />
            </div>
            <label class="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer">
              <input type="checkbox" v-model="editForm.is_active" class="rounded" />
              启用
            </label>
          </div>

          <!-- 密码管理区 -->
          <div class="mt-4 border border-gray-200 rounded p-3 space-y-3">
            <div class="text-sm font-medium text-gray-700">🔒 密码管理</div>
            <!-- 修改为新密码 -->
            <div class="grid grid-cols-2 gap-2">
              <input v-model="newPwd" type="password" placeholder="输入新密码"
                class="px-3 py-1.5 border border-gray-300 rounded text-sm" />
              <input v-model="newPwdConfirm" type="password" placeholder="再次输入新密码"
                class="px-3 py-1.5 border border-gray-300 rounded text-sm" />
            </div>
            <button @click="doResetPassword" :disabled="pwdSaving"
              class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm hover:bg-gray-50 disabled:opacity-50 transition">
              🔒 {{ pwdSaving ? '修改中...' : '修改密码' }}
            </button>
            <div v-if="pwdMsg" :class="['text-xs', pwdOk ? 'text-green-600' : 'text-red-500']">{{ pwdMsg }}</div>
          </div>

          <!-- 操作按钮 -->
          <div class="mt-5 space-y-2">
            <button @click="doSaveEdit" :disabled="saving"
              class="w-full px-4 py-2 bg-primary text-white rounded text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition">
              💾 {{ saving ? '保存中...' : '保存信息' }}
            </button>
            <template v-if="editTarget.username !== 'admin'">
              <div class="grid grid-cols-2 gap-2">
                <button @click="deactivateTarget = editTarget"
                  class="px-4 py-2 bg-amber-50 text-amber-700 border border-amber-200 rounded text-sm hover:bg-amber-100 transition">
                  ⏸️ 停用
                </button>
                <button @click="deleteTarget = editTarget"
                  class="px-4 py-2 bg-red-50 text-red-600 border border-red-200 rounded text-sm hover:bg-red-100 transition">
                  🗑️ 删除
                </button>
              </div>
            </template>
            <p v-else class="text-xs text-gray-400 text-center">🛡️ 系统管理员账号不可操作</p>
          </div>
          <div v-if="editMsg" :class="['text-xs mt-2', editOk ? 'text-green-600' : 'text-red-500']">{{ editMsg }}</div>
        </div>
      </div>
    </Teleport>

    <!-- 停用确认弹窗 -->
    <ConfirmDialog
      :visible="!!deactivateTarget"
      title="停用账号"
      :message="`确定停用账号「${deactivateTarget?.username}」吗？停用为软删除，数据保留。`"
      confirm-text="停用"
      confirm-class="bg-amber-600 hover:bg-amber-700"
      :loading="deactivating"
      @confirm="doDeactivate"
      @cancel="deactivateTarget = null"
    />

    <!-- 删除确认弹窗 -->
    <ConfirmDialog
      :visible="!!deleteTarget"
      title="删除账号"
      :message="`确定要永久删除账号「${deleteTarget?.username}」吗？此操作不可恢复，用户数据将被彻底清除。`"
      confirm-text="永久删除"
      :loading="deleting"
      @confirm="doDelete"
      @cancel="deleteTarget = null"
    />

    <!-- 1009 离职交接确认弹窗 -->
    <ConfirmDialog
      :visible="handoverConfirmVisible"
      title="确认离职交接"
      :message="handoverConfirmMessage"
      confirm-text="确认移交"
      :loading="handoverSubmitting"
      @confirm="doHandover"
      @cancel="handoverConfirmVisible = false"
    />
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import KBManager from '@/components/admin/KBManager.vue'
import ComplaintTable from '@/components/admin/ComplaintTable.vue'
import * as usersApi from '@/api/users'
import * as settingsApi from '@/api/settings'
import type { ManagedUser, UserMeta, SmtpConfig, DingtalkConfig, HandoverPreview } from '@/types/api'

const tabs = [
  { key: 'list' as const, label: '👥 用户列表' },
  { key: 'create' as const, label: '➕ 新增用户' },
  { key: 'handover' as const, label: '🔄 离职交接' },
  { key: 'kb' as const, label: '📚 知识库管理' },
  { key: 'complaints' as const, label: '📋 工单管理' },
  { key: 'email' as const, label: '📧 邮箱设置' },
  { key: 'dingtalk' as const, label: '📱 钉钉通知' },
]
const activeTab = ref<'list' | 'create' | 'handover' | 'kb' | 'complaints' | 'email' | 'dingtalk'>('list')

// 0819 六角色彩徽
const ROLE_COLORS: Record<string, string> = {
  '管理员':   'bg-red-50 text-red-700 ring-1 ring-red-200',
  '客服':     'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
  '客服主管': 'bg-violet-50 text-violet-700 ring-1 ring-violet-200',
  '办理人':   'bg-cyan-50 text-cyan-700 ring-1 ring-cyan-200',
  '审批人':   'bg-blue-50 text-blue-700 ring-1 ring-blue-200',
  '承接人':   'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
}

// ── 元数据 ─────────────────────────────────
const meta = ref<UserMeta>({ roles: [] })

async function fetchMeta() {
  try {
    const r = await usersApi.getUserMeta()
    if (r.data?.success) meta.value = r.data.data
  } catch (e) { console.error('fetchMeta error:', e) }
}

// ── 用户列表 ────────────────────────────────
const users = ref<ManagedUser[]>([])
const loading = ref(false)
const roleFilter = ref('')
const showInactive = ref(false)

const activeCount = computed(() => users.value.filter(u => u.is_active).length)

async function fetchUsers() {
  loading.value = true
  try {
    const r = await usersApi.listUsers({
      role: roleFilter.value,
      include_inactive: showInactive.value,
    })
    if (r.data?.success) users.value = r.data.data || []
  } catch (e) { console.error('fetchUsers error:', e) }
  finally { loading.value = false }
}

// ── 新增用户（0819 角色下拉 + 职位必填；0824 钉钉UserID选填） ──
const createForm = reactive({
  username: '', display_name: '', password: '', passwordConfirm: '',
  role: '', position: '', dingtalk_userid: '',
})
const creating = ref(false)
const createMsg = ref('')
const createOk = ref(false)

async function doCreate() {
  createMsg.value = ''
  if (!createForm.username || !createForm.display_name || !createForm.password) {
    createOk.value = false; createMsg.value = '账号、显示名和密码不能为空'; return
  }
  if (createForm.password.length < 4) {
    createOk.value = false; createMsg.value = '密码至少4位'; return
  }
  if (createForm.password !== createForm.passwordConfirm) {
    createOk.value = false; createMsg.value = '两次密码不一致'; return
  }
  if (!createForm.role) {
    createOk.value = false; createMsg.value = '请选择角色'; return
  }
  if (!createForm.position.trim()) {
    createOk.value = false; createMsg.value = '请填写公司职位'; return
  }
  creating.value = true
  try {
    const r = await usersApi.createUser({
      username: createForm.username.trim(),
      password: createForm.password,
      display_name: createForm.display_name.trim(),
      role: createForm.role,
      position: createForm.position.trim(),
      dingtalk_userid: createForm.dingtalk_userid.trim(),
    })
    if (r.data?.success) {
      createOk.value = true
      createMsg.value = `✅ 账号「${createForm.username}」创建成功！`
      Object.assign(createForm, { username: '', display_name: '', password: '', passwordConfirm: '', role: '', position: '', dingtalk_userid: '' })
      fetchUsers()
    }
  } catch (e: any) {
    createOk.value = false
    createMsg.value = e?.response?.data?.detail || '创建失败，请检查账号是否重复'
  } finally { creating.value = false }
}

// ── 离职交接（1009）────────────────────────
const handoverFrom = ref<number | ''>('')
const handoverTo = ref<number | ''>('')
const handoverDeactivate = ref(true)
const handoverPreview = ref<HandoverPreview | null>(null)
const handoverPreviewLoading = ref(false)
const handoverConfirmVisible = ref(false)
const handoverSubmitting = ref(false)
const handoverMsg = ref('')
const handoverOk = ref(false)

// 全量用户（含已停用）——首次进入交接页签时加载
const allUsers = ref<ManagedUser[]>([])
// 离职人员候选：排除 admin（后端同样拦截）
const handoverCandidates = computed(() => allUsers.value.filter(u => u.username !== 'admin'))
// 接收人候选：在职且不等于离职人员
const handoverReceivers = computed(() =>
  allUsers.value.filter(u => u.is_active && u.id !== handoverFrom.value))
const fromUserIsActive = computed(() =>
  !!allUsers.value.find(u => u.id === handoverFrom.value)?.is_active)

const handoverConfirmMessage = computed(() => {
  const p = handoverPreview.value
  if (!p) return ''
  const suffix = handoverDeactivate.value && fromUserIsActive.value
    ? `；「${p.from_user.display_name}」的账号将同时停用（软删除，数据保留）` : ''
  return `确定将 ${p.from_user.display_name} 名下 ${p.total_complaints} 客户工程师单移交给 ${p.to_user.display_name} 吗？各工单的历史过程记录将完整保留${suffix}。`
})

async function fetchAllUsers() {
  try {
    const r = await usersApi.listUsers({ include_inactive: true })
    if (r.data?.success) allUsers.value = r.data.data || []
  } catch (e) { console.error('fetchAllUsers error:', e) }
}

watch(activeTab, (t) => {
  if (t === 'handover' && !allUsers.value.length) fetchAllUsers()
})

async function onHandoverChange() {
  handoverPreview.value = null
  handoverMsg.value = ''
  if (!handoverFrom.value || !handoverTo.value) return
  handoverPreviewLoading.value = true
  try {
    const r = await usersApi.previewHandover(Number(handoverFrom.value), Number(handoverTo.value))
    if (r.data?.success) handoverPreview.value = r.data.data
  } catch (e: any) {
    handoverOk.value = false
    handoverMsg.value = e?.response?.data?.detail || '预览失败，请稍后重试'
  } finally { handoverPreviewLoading.value = false }
}

function confirmHandover() {
  if (!handoverPreview.value) return
  handoverMsg.value = ''
  handoverConfirmVisible.value = true
}

async function doHandover() {
  handoverSubmitting.value = true
  try {
    const deactivate = handoverDeactivate.value && fromUserIsActive.value
    const r = await usersApi.executeHandover(
      Number(handoverFrom.value), Number(handoverTo.value), deactivate)
    if (r.data?.success) {
      const d = r.data.data
      handoverOk.value = true
      handoverMsg.value = `✅ 交接完成：${d.total_complaints} 客户工程师单已移交给 ${d.to_user.display_name}` +
        (d.deactivated ? '，离职账号已停用' : '') + '（历史过程记录在各工单时间线完整可查）'
      handoverConfirmVisible.value = false
      handoverPreview.value = null
      handoverFrom.value = ''
      handoverTo.value = ''
      await fetchAllUsers()
      fetchUsers()
    }
  } catch (e: any) {
    handoverOk.value = false
    handoverConfirmVisible.value = false
    handoverMsg.value = e?.response?.data?.detail || '交接失败，请稍后重试'
  } finally { handoverSubmitting.value = false }
}

// ── 编辑用户（0819 角色 + 职位）──────────────
const editTarget = ref<ManagedUser | null>(null)
const editForm = reactive({
  display_name: '', role: '', position: '', dingtalk_userid: '', is_active: true,
})
const saving = ref(false)
const editMsg = ref('')
const editOk = ref(false)

function openEdit(u: ManagedUser) {
  editTarget.value = u
  Object.assign(editForm, {
    display_name: u.display_name, role: u.role, position: u.position,
    dingtalk_userid: u.dingtalk_userid || '', is_active: u.is_active,
  })
  // 重置密码区状态
  newPwd.value = ''
  newPwdConfirm.value = ''
  pwdMsg.value = ''
  editMsg.value = ''
}

async function doSaveEdit() {
  if (!editTarget.value) return
  saving.value = true; editMsg.value = ''
  try {
    const r = await usersApi.updateUser(editTarget.value.id, {
      display_name: editForm.display_name,
      role: editForm.role,
      position: editForm.position,
      dingtalk_userid: editForm.dingtalk_userid.trim(),
      is_active: editForm.is_active,
    })
    if (r.data?.success) {
      editOk.value = true
      editMsg.value = '✅ 已保存'
      await fetchUsers()
      // 同步列表数据到编辑目标
      const fresh = users.value.find(u => u.id === editTarget.value!.id)
      if (fresh) editTarget.value = fresh
    }
  } catch (e: any) {
    editOk.value = false
    editMsg.value = e?.response?.data?.detail || '保存失败'
  } finally { saving.value = false }
}

// ── 密码管理 ────────────────────────────────
const newPwd = ref('')
const newPwdConfirm = ref('')
const pwdSaving = ref(false)
const pwdMsg = ref('')
const pwdOk = ref(false)

async function doResetPassword() {
  if (!editTarget.value) return
  pwdMsg.value = ''
  // 来源：v2.1 6_系统管理.py 143-149 行 — 校验规则
  if (!newPwd.value) { pwdOk.value = false; pwdMsg.value = '请输入新密码'; return }
  if (newPwd.value.length < 4) { pwdOk.value = false; pwdMsg.value = '密码至少 4 位'; return }
  if (newPwd.value !== newPwdConfirm.value) { pwdOk.value = false; pwdMsg.value = '两次密码不一致'; return }
  pwdSaving.value = true
  try {
    const r = await usersApi.resetUserPassword(editTarget.value.id, newPwd.value)
    if (r.data?.success) {
      pwdOk.value = true
      pwdMsg.value = `✅ 密码已修改为：${newPwd.value}`
      newPwd.value = ''
      newPwdConfirm.value = ''
    }
  } catch (e: any) {
    pwdOk.value = false
    pwdMsg.value = e?.response?.data?.detail || '修改失败'
  } finally { pwdSaving.value = false }
}

// ── 停用账号 ────────────────────────────────
const deactivateTarget = ref<ManagedUser | null>(null)
const deactivating = ref(false)

async function doDeactivate() {
  if (!deactivateTarget.value) return
  deactivating.value = true
  try {
    const r = await usersApi.deactivateUser(deactivateTarget.value.id)
    if (r.data?.success) {
      editTarget.value = null
      await fetchUsers()
    }
  } catch (e: any) {
    editOk.value = false
    editMsg.value = e?.response?.data?.detail || '停用失败'
  } finally {
    deactivating.value = false
    deactivateTarget.value = null
  }
}

// ── 删除账号 ────────────────────────────────
const deleteTarget = ref<ManagedUser | null>(null)
const deleting = ref(false)

async function doDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    const r = await usersApi.deleteUser(deleteTarget.value.id)
    if (r.data?.success) {
      editTarget.value = null
      await fetchUsers()
    }
  } catch (e: any) {
    editMsg.value = e?.response?.data?.detail || '删除失败'
  } finally {
    deleting.value = false
    deleteTarget.value = null
  }
}

onMounted(() => { fetchMeta(); fetchUsers() })

// ── 0811 邮箱设置 ────────────────────────────────
const smtpForm = reactive({
  smtp_host: '',
  smtp_port: 587,
  smtp_user: '',
  smtp_password: '',
  smtp_from: '',
})
const smtpConfig = reactive<SmtpConfig>({
  smtp_host: '', smtp_port: 587, smtp_user: '', smtp_password: '', smtp_from: '', is_configured: false,
})
const smtpLoading = ref(false)
const smtpSaving = ref(false)
const smtpTesting = ref(false)
const smtpMsg = ref('')
const smtpOk = ref(false)
const showSmtpPassword = ref(false)
const smtpTabVisited = ref(false)

async function fetchSmtpConfig() {
  smtpLoading.value = true
  try {
    const r = await settingsApi.getSmtpConfig()
    if (r.data?.success && r.data?.data) {
      Object.assign(smtpConfig, r.data.data)
      // 回填表单（密码已脱敏，保留空让用户自行输入）
      smtpForm.smtp_host = smtpConfig.smtp_host
      smtpForm.smtp_port = smtpConfig.smtp_port
      smtpForm.smtp_user = smtpConfig.smtp_user
      smtpForm.smtp_password = ''   // 不填回脱敏密码
      smtpForm.smtp_from = smtpConfig.smtp_from
    }
  } catch (e: any) {
    smtpOk.value = false
    smtpMsg.value = e?.response?.data?.detail || '加载配置失败'
  } finally { smtpLoading.value = false }
}

async function doSaveSmtp() {
  smtpMsg.value = ''
  if (!smtpForm.smtp_host || !smtpForm.smtp_user || !smtpForm.smtp_from) {
    smtpOk.value = false; smtpMsg.value = '服务器地址、用户名和发件人不能为空'; return
  }
  smtpSaving.value = true
  try {
    const r = await settingsApi.updateSmtpConfig({ ...smtpForm })
    if (r.data?.success) {
      smtpOk.value = true
      smtpMsg.value = '✅ SMTP 配置已保存并生效'
      if (r.data?.data) Object.assign(smtpConfig, r.data.data)
    }
  } catch (e: any) {
    smtpOk.value = false
    smtpMsg.value = e?.response?.data?.detail || '保存失败'
  } finally { smtpSaving.value = false }
}

async function doTestSmtp() {
  smtpMsg.value = ''
  if (!smtpForm.smtp_host || !smtpForm.smtp_user || !smtpForm.smtp_password) {
    smtpOk.value = false; smtpMsg.value = '请先填写服务器地址、用户名和密码'; return
  }
  smtpTesting.value = true
  try {
    const r = await settingsApi.testSmtpConnection({ ...smtpForm })
    smtpOk.value = r.data?.success || false
    smtpMsg.value = r.data?.data?.message || r.data?.message || '测试完成'
  } catch (e: any) {
    smtpOk.value = false
    smtpMsg.value = e?.response?.data?.detail || '测试请求失败'
  } finally { smtpTesting.value = false }
}

// 懒加载：切换到邮箱设置 tab 时首次拉取配置
watch(activeTab, (val) => {
  if (val === 'email' && !smtpTabVisited.value) {
    smtpTabVisited.value = true
    fetchSmtpConfig()
  }
  if (val === 'dingtalk' && !dingtalkTabVisited.value) {
    dingtalkTabVisited.value = true
    fetchDingtalkConfig()
  }
})

// ── 0824 钉钉通知设置 ────────────────────────────
const dingtalkForm = reactive({
  enabled: false,
  app_key: '',
  app_secret: '',
  agent_id: '',
  public_base_url: '',
  dry_run: false,
})
const dingtalkConfig = reactive<DingtalkConfig>({
  enabled: false, app_key: '', app_secret: '', agent_id: '',
  public_base_url: '', dry_run: false, is_configured: false,
})
const dingtalkLoading = ref(false)
const dingtalkSaving = ref(false)
const dingtalkTesting = ref(false)
const dingtalkMsg = ref('')
const dingtalkOk = ref(false)
const showDingtalkSecret = ref(false)
const dingtalkTabVisited = ref(false)

async function fetchDingtalkConfig() {
  dingtalkLoading.value = true
  try {
    const r = await settingsApi.getDingtalkConfig()
    if (r.data?.success && r.data?.data) {
      Object.assign(dingtalkConfig, r.data.data)
      // 回填表单（密钥已脱敏，保留空让用户自行输入）
      dingtalkForm.enabled = dingtalkConfig.enabled
      dingtalkForm.app_key = dingtalkConfig.app_key
      dingtalkForm.app_secret = ''   // 不填回脱敏密钥
      dingtalkForm.agent_id = dingtalkConfig.agent_id
      dingtalkForm.public_base_url = dingtalkConfig.public_base_url
      dingtalkForm.dry_run = dingtalkConfig.dry_run
    }
  } catch (e: any) {
    dingtalkOk.value = false
    dingtalkMsg.value = e?.response?.data?.detail || '加载配置失败'
  } finally { dingtalkLoading.value = false }
}

async function doSaveDingtalk() {
  dingtalkMsg.value = ''
  if (dingtalkForm.enabled
    && (!dingtalkForm.app_key || !dingtalkForm.agent_id || !dingtalkForm.public_base_url)) {
    dingtalkOk.value = false; dingtalkMsg.value = '启用时 AppKey、AgentId 和系统访问地址不能为空'; return
  }
  dingtalkSaving.value = true
  try {
    const r = await settingsApi.updateDingtalkConfig({ ...dingtalkForm })
    if (r.data?.success) {
      dingtalkOk.value = true
      dingtalkMsg.value = '✅ 钉钉配置已保存并生效'
      if (r.data?.data) Object.assign(dingtalkConfig, r.data.data)
    }
  } catch (e: any) {
    dingtalkOk.value = false
    dingtalkMsg.value = e?.response?.data?.detail || '保存失败'
  } finally { dingtalkSaving.value = false }
}

async function doTestDingtalk() {
  dingtalkMsg.value = ''
  // 密钥留空时回退当前已保存值（后端同样处理）
  if (!dingtalkForm.app_key || (!dingtalkForm.app_secret && !dingtalkConfig.app_key)) {
    dingtalkOk.value = false; dingtalkMsg.value = '请先填写 AppKey 和 AppSecret'; return
  }
  dingtalkTesting.value = true
  try {
    const r = await settingsApi.testDingtalkConnection({ ...dingtalkForm })
    dingtalkOk.value = r.data?.success || false
    dingtalkMsg.value = r.data?.data?.message || r.data?.message || '测试完成'
  } catch (e: any) {
    dingtalkOk.value = false
    dingtalkMsg.value = e?.response?.data?.detail || '测试请求失败'
  } finally { dingtalkTesting.value = false }
}

// ── 0825 手机号查 UserID 小工具 ──────────────────
const useridLookup = reactive({
  mobile: '', loading: false, msg: '', ok: false, userid: '', name: '',
})

async function doLookupUserid() {
  useridLookup.msg = ''
  useridLookup.userid = ''
  useridLookup.name = ''
  const m = useridLookup.mobile.trim()
  if (!/^\d{11}$/.test(m)) {
    useridLookup.ok = false; useridLookup.msg = '请输入 11 位手机号'; return
  }
  // 凭证校验与「测试凭证」一致：表单值优先，AppSecret 留空回退已保存值
  if (!dingtalkForm.app_key || (!dingtalkForm.app_secret && !dingtalkConfig.app_key)) {
    useridLookup.ok = false; useridLookup.msg = '请先填写 AppKey 和 AppSecret（或保存配置）'; return
  }
  useridLookup.loading = true
  try {
    const r = await settingsApi.lookupDingtalkUserid({
      mobile: m,
      app_key: dingtalkForm.app_key,
      app_secret: dingtalkForm.app_secret,
    })
    const d = r.data?.data
    useridLookup.ok = !!r.data?.success
    useridLookup.msg = d?.message || r.data?.message || '查询完成'
    useridLookup.userid = d?.userid || ''
    useridLookup.name = d?.name || ''
  } catch (e: any) {
    useridLookup.ok = false
    useridLookup.msg = e?.response?.data?.detail || '查询请求失败'
  } finally { useridLookup.loading = false }
}

async function copyUserid() {
  try {
    await navigator.clipboard.writeText(useridLookup.userid)
    useridLookup.ok = true
    useridLookup.msg = '✅ 已复制到剪贴板'
  } catch {
    // http 非安全上下文等场景 clipboard API 不可用：提示手动选择
    useridLookup.ok = false
    useridLookup.msg = '自动复制失败，请手动选中复制'
  }
}
</script>
