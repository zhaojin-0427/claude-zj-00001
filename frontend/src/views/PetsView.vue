<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ownersApi, petsApi } from '../api'
import type { Owner, Pet } from '../api/types'
import { SPECIES_EMOJI, STATUS_META } from '../utils/format'

const router = useRouter()
const loading = ref(false)
const pets = ref<Pet[]>([])
const owners = ref<Owner[]>([])
const q = ref('')
const species = ref('')

const petDialog = ref(false)
const ownerDialog = ref(false)
const saving = ref(false)

const petForm = reactive({
  owner_id: undefined as number | undefined,
  name: '',
  species: '犬',
  breed: '',
  gender: '公',
  birth_date: '',
  color: '',
  microchip: '',
  neutered: false,
})
const ownerForm = reactive({ name: '', phone: '', address: '' })

async function load() {
  loading.value = true
  try {
    pets.value = await petsApi.list({ species: species.value, q: q.value })
  } finally {
    loading.value = false
  }
}

async function openPetDialog() {
  owners.value = await ownersApi.list()
  Object.assign(petForm, {
    owner_id: owners.value[0]?.id, name: '', species: '犬', breed: '',
    gender: '公', birth_date: '', color: '', microchip: '', neutered: false,
  })
  petDialog.value = true
}

async function submitPet() {
  if (!petForm.owner_id || !petForm.name) {
    ElMessage.warning('请选择主人并填写宠物名')
    return
  }
  saving.value = true
  try {
    await petsApi.create({ ...petForm, neutered: petForm.neutered ? 1 : 0 })
    ElMessage.success('宠物档案已建立')
    petDialog.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function submitOwner() {
  if (!ownerForm.name || !ownerForm.phone) {
    ElMessage.warning('姓名和手机号必填')
    return
  }
  saving.value = true
  try {
    const res = await ownersApi.create({ ...ownerForm })
    ElMessage.success('主人登记成功')
    ownerDialog.value = false
    owners.value = await ownersApi.list()
    petForm.owner_id = res.id
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="filter-bar">
    <el-input v-model="q" placeholder="搜索宠物名 / 主人 / 手机号" clearable
              style="width: 260px" @keyup.enter="load" @clear="load">
      <template #prefix><el-icon><Search /></el-icon></template>
    </el-input>
    <el-select v-model="species" placeholder="全部物种" clearable style="width: 140px"
               @change="load">
      <el-option label="犬" value="犬" />
      <el-option label="猫" value="猫" />
      <el-option label="兔" value="兔" />
    </el-select>
    <el-button type="primary" @click="load">查询</el-button>
    <div style="flex:1"></div>
    <el-button type="primary" :icon="'Plus'" @click="openPetDialog">新建宠物档案</el-button>
  </div>

  <el-table :data="pets" v-loading="loading" class="card-shadow" stripe
            @row-click="(row: Pet) => router.push(`/pets/${row.id}`)"
            :row-style="{ cursor: 'pointer' }">
    <el-table-column label="宠物" min-width="170">
      <template #default="{ row }">
        <div style="display:flex;align-items:center;gap:10px">
          <el-avatar :size="40" style="background:#fdf6ec;font-size:22px">
            {{ SPECIES_EMOJI[row.species] || '🐾' }}
          </el-avatar>
          <div>
            <strong>{{ row.name }}</strong>
            <div style="color:#909399;font-size:12px">{{ row.breed || '品种未填' }}</div>
          </div>
        </div>
      </template>
    </el-table-column>
    <el-table-column prop="species" label="物种" width="70" />
    <el-table-column label="性别 / 绝育" width="110">
      <template #default="{ row }">
        {{ row.gender }}
        <el-tag v-if="row.neutered" size="small" type="info">已绝育</el-tag>
      </template>
    </el-table-column>
    <el-table-column prop="birth_date" label="出生日期" width="120" />
    <el-table-column label="主人" width="110">
      <template #default="{ row }">{{ row.owner_name }}</template>
    </el-table-column>
    <el-table-column prop="owner_phone" label="联系电话" width="130" />
    <el-table-column prop="microchip" label="芯片号" min-width="130" />
    <el-table-column label="操作" width="100" fixed="right">
      <template #default="{ row }">
        <el-button link type="primary" @click.stop="router.push(`/pets/${row.id}`)">
          完整档案
        </el-button>
      </template>
    </el-table-column>
  </el-table>

  <!-- 新建宠物 -->
  <el-dialog v-model="petDialog" title="新建宠物档案" width="560px">
    <el-form :model="petForm" label-width="90px">
      <el-form-item label="主人" required>
        <el-select v-model="petForm.owner_id" placeholder="选择主人" style="flex:1">
          <el-option v-for="o in owners" :key="o.id"
                     :label="`${o.name}（${o.phone}）`" :value="o.id" />
        </el-select>
        <el-button link type="primary" @click="ownerDialog = true">+ 新登记主人</el-button>
      </el-form-item>
      <el-form-item label="宠物名" required>
        <el-input v-model="petForm.name" />
      </el-form-item>
      <el-form-item label="物种">
        <el-radio-group v-model="petForm.species">
          <el-radio-button label="犬" />
          <el-radio-button label="猫" />
          <el-radio-button label="兔" />
        </el-radio-group>
      </el-form-item>
      <el-form-item label="品种">
        <el-input v-model="petForm.breed" placeholder="如 金毛寻回犬" />
      </el-form-item>
      <el-form-item label="性别">
        <el-radio-group v-model="petForm.gender">
          <el-radio label="公">公</el-radio>
          <el-radio label="母">母</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="出生日期">
        <el-date-picker v-model="petForm.birth_date" type="date" value-format="YYYY-MM-DD"
                        placeholder="选择日期" style="width:100%" />
      </el-form-item>
      <el-form-item label="毛色">
        <el-input v-model="petForm.color" />
      </el-form-item>
      <el-form-item label="芯片号">
        <el-input v-model="petForm.microchip" />
      </el-form-item>
      <el-form-item label="是否绝育">
        <el-switch v-model="petForm.neutered" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="petDialog = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submitPet">保存</el-button>
    </template>
  </el-dialog>

  <!-- 新登记主人 -->
  <el-dialog v-model="ownerDialog" title="登记宠物主人" width="460px" append-to-body>
    <el-form :model="ownerForm" label-width="80px">
      <el-form-item label="姓名" required>
        <el-input v-model="ownerForm.name" />
      </el-form-item>
      <el-form-item label="手机号" required>
        <el-input v-model="ownerForm.phone" />
      </el-form-item>
      <el-form-item label="地址">
        <el-input v-model="ownerForm.address" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="ownerDialog = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submitOwner">保存</el-button>
    </template>
  </el-dialog>
</template>
